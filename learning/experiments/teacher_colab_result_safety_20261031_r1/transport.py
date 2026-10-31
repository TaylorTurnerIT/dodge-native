"""Bounded, redacted Contents API transfers for exact-owned artifact paths only.

Each request runs in a reaped subprocess. Private proxy credentials travel on
stdin, never argv, receipts or exception text. No account, assignment, kernel,
allocation, execution or retry API is implemented. Production requires HTTPS.
"""
import base64
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlencode, urlsplit

MAX_RESPONSE_BYTES = 2 * 1024**2
REQUEST_SECONDS = 15
READ_PATH = re.compile(r"(?:manifests|ready)/[0-9]{6}\.json|chunks/[0-9a-f]{64}\.bin|stage-exit\.json")
ACK_PATH = re.compile(r"acks/[0-9]{6}\.json")


class TransportError(ValueError):
    def __init__(self, operation, failure_class, http_status=None):
        self.operation, self.failure_class, self.http_status = operation, failure_class, http_status
        super().__init__("Contents transfer failed: " + operation + "/" + failure_class
                         + (" HTTP " + str(http_status) if http_status is not None else ""))


def _child(value):
    """One HTTP request, zero redirects/retries, finite response and socket bounds."""
    connection = None
    try:
        parsed = urlsplit(value["url"])
        fixture = value.get("fixture_only") is True
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("URL format")
        if parsed.scheme == "https":
            connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=2)
        elif fixture and parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1"):
            connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
        else:
            raise ValueError("HTTPS required")
        remote = value["root"].rstrip("/") + "/" + value["relative"]
        query = {"authuser": "0", "colab-runtime-proxy-token": value["token"]}
        if value["method"] == "GET":
            query["content"] = "1"
        path = parsed.path.rstrip("/") + "/api/contents/" + quote(remote.strip("/"), safe="/")
        payload = None
        if value["method"] == "PUT":
            text = base64.b64decode(value["data"], validate=True).decode("utf-8")
            payload = json.dumps(dict(type="file", format="text", name=Path(remote).name,
                                      path=remote, content=text)).encode()
        connection.connect()
        connection.sock.settimeout(5)
        connection.request(value["method"], path + "?" + urlencode(query), body=payload,
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200 and response.status != 201:
            return dict(ok=False, failure_class="http_status", http_status=response.status)
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            return dict(ok=False, failure_class="response_size_cap", http_status=response.status)
        body = json.loads(data)
        if value["method"] == "PUT":
            return dict(ok=True)
        if body.get("type") != "file" or body.get("format") not in ("text", "base64"):
            return dict(ok=False, failure_class="file_format", http_status=response.status)
        content = body.get("content")
        if not isinstance(content, str):
            return dict(ok=False, failure_class="file_format", http_status=response.status)
        decoded = (base64.b64decode(content, validate=True) if body["format"] == "base64"
                   else content.encode("utf-8"))
        if len(decoded) > 1024**2:
            return dict(ok=False, failure_class="decoded_size_cap", http_status=response.status)
        return dict(ok=True, data=base64.b64encode(decoded).decode("ascii"))
    except TimeoutError:
        return dict(ok=False, failure_class="socket_timeout")
    except (OSError, http.client.HTTPException):
        return dict(ok=False, failure_class="connection_error")
    except (ValueError, KeyError, TypeError):
        return dict(ok=False, failure_class="response_format")
    finally:
        if connection is not None:
            connection.close()


class ContentsTransport:
    def __init__(self, *, session_provider, endpoint, remote_root, verify_owned_endpoint, guard,
                 python=sys.executable, fixture_only=False):
        session = session_provider()
        if session.endpoint != endpoint or not re.fullmatch(r"/content/[A-Za-z0-9_.-]+/exports", remote_root):
            raise TransportError("ownership", "identity_mismatch")
        self.session_provider, self.endpoint, self.root = session_provider, endpoint, remote_root
        self.verify_owned_endpoint, self.guard = verify_owned_endpoint, guard
        self.python, self.fixture_only = python, fixture_only

    def _call(self, relative, *, data=None, optional=False):
        operation = "read" if data is None else "acknowledge"
        if not (READ_PATH if data is None else ACK_PATH).fullmatch(relative):
            raise TransportError(operation, "path_not_allowed")
        if data is not None and len(data) > 4096:
            raise TransportError(operation, "ack_size_cap")
        self.guard()
        self.verify_owned_endpoint(self.endpoint)
        # Read the sole dispatcher's current private session, rather than
        # retaining an expired proxy token for a multi-hour run.
        session = self.session_provider()
        if session is None or session.endpoint != self.endpoint:
            raise TransportError(operation, "identity_mismatch")
        request = dict(url=session.url, token=session.token, root=self.root,
                       relative=relative, method="GET" if data is None else "PUT",
                       fixture_only=self.fixture_only)
        if data is not None:
            request["data"] = base64.b64encode(data).decode("ascii")
        try:
            child = subprocess.Popen([self.python, "-B", str(Path(__file__).resolve()), "--child"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                output, _ = child.communicate(json.dumps(request).encode(), timeout=REQUEST_SECONDS)
            except BaseException:
                child.kill()
                child.wait()
                raise
            if child.returncode or len(output) > MAX_RESPONSE_BYTES:
                raise TransportError(operation, "child_failure")
            result = json.loads(output)
        except subprocess.TimeoutExpired:
            raise TransportError(operation, "total_deadline") from None
        except (OSError, ValueError) as error:
            if isinstance(error, TransportError):
                raise
            raise TransportError(operation, "child_protocol") from None
        self.guard()
        if not result["ok"]:
            if optional and result.get("http_status") == 404:
                return None
            raise TransportError(operation, result["failure_class"], result.get("http_status"))
        return base64.b64decode(result["data"], validate=True) if data is None else None

    def get_json(self, relative):
        return self._call(relative)

    def get_chunk(self, relative):
        return self._call(relative)

    def put_ack(self, relative, data):
        return self._call(relative, data=data)

    def next_pointer(self, sequence):
        raw = self._call("ready/%06d.json" % sequence, optional=True)
        return None if raw is None else json.loads(raw)

    def read_stage_exit(self):
        return self._call("stage-exit.json", optional=True)


if __name__ == "__main__":
    # Only a private parent pipe may drive this helper; it has no cloud CLI.
    if sys.argv[1:] != ["--child"]:
        raise SystemExit("Source-only transfer helper; no allocation or training entry")
    try:
        raw = sys.stdin.buffer.read(16385)
        result = _child(json.loads(raw)) if len(raw) <= 16384 else dict(ok=False, failure_class="input_size_cap")
    except BaseException:
        result = dict(ok=False, failure_class="child_protocol")
    sys.stdout.write(json.dumps(result))
