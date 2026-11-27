"""Token-protected localhost relay for bounded native Dodge frame streams."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

POLICIES = {"lookahead", "landscape", "hnn", "potential", "flee", "random", "neutral"}
IDLE_SECONDS = 45
START_TIMEOUT = 90
MAX_CHUNK = 120
READ_TIMEOUT = 8
MAX_QUEUED_LINES = MAX_CHUNK * 2
_RELAYS = {}
_RELAYS_LOCK = threading.Lock()


def get_relay(binary, hnn_model=None):
    key = (str(binary), str(hnn_model) if hnn_model else None)
    with _RELAYS_LOCK:
        if key not in _RELAYS:
            _RELAYS[key] = Relay(*key)
        return _RELAYS[key]


class _Session:
    def __init__(self, process: subprocess.Popen, meta: dict, lines, reader):
        self.process = process
        self.meta = meta
        self.lock = threading.Lock()
        self.touched = time.monotonic()
        self.ended = False
        self.result = None
        self.lines = lines
        self.frames = 0
        self.reader = reader
        self.discard_output = threading.Event()

    def stop(self):
        self.discard_output.set()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=2)


class Relay:
    """Runs at most one native process and streams frames on demand."""

    def __init__(self, binary, hnn_model=None):
        self.binary = str(binary)
        self.hnn_model = str(hnn_model) if hnn_model else None
        self.token = secrets.token_urlsafe(24)
        self._session = None
        self._guard = threading.Lock()
        self._start_lock = threading.Lock()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _send(self, status, value):
                body = json.dumps(value, separators=(",", ":")).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                query = {key: values[-1] for key, values in parse_qs(url.query).items()}
                if not secrets.compare_digest(query.get("k", ""), relay.token):
                    self._send(403, {"error": "unauthorized"})
                    return
                try:
                    if url.path == "/start":
                        self._send(200, relay.start(query))
                    elif url.path == "/next":
                        self._send(200, relay.next(query))
                    elif url.path == "/keepalive":
                        self._send(200, relay.keepalive(query))
                    elif url.path == "/stop":
                        self._send(200, relay.stop(query))
                    else:
                        self._send(404, {"error": "not found"})
                except ValueError as error:
                    self._send(400, {"error": str(error)})
                except Exception:
                    self._send(500, {"error": "native relay failed"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        threading.Thread(target=self._reap, daemon=True).start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    @staticmethod
    def _integer(query, name, low, high, default):
        try:
            value = int(query.get(name, default))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must be an integer") from error
        if not low <= value <= high:
            raise ValueError(f"{name} must be from {low} to {high}")
        return value

    def start(self, query):
        policy = query.get("policy", "lookahead")
        if policy not in POLICIES:
            raise ValueError("unknown policy")
        if not Path(self.binary).is_file():
            raise ValueError("dodge-danger binary is missing")
        if policy == "hnn" and (not self.hnn_model or not Path(self.hnn_model).is_file()):
            raise ValueError("HNN physics model is missing")
        if os.getloadavg()[0] > 8.0:
            raise ValueError("live run is paused because one-minute system load exceeds 8")
        args = ["nice", "-n", "19", self.binary, "--stream", "--native-pixels",
                "--policy", policy,
                "--seed", str(self._integer(query, "seed", 0, 4_000_000_000, 42)),
                "--difficulty", str(self._integer(query, "difficulty", 1, 3, 2)),
                "--horizon", "36", "--heat-every", "8"]
        if policy == "hnn":
            args += ["--physics-model", self.hnn_model, "--grid", "12", "--goal-every", "16", "--heat-every", "16"]
        with self._start_lock:
            with self._guard:
                previous = self._session
                self._session = None
            if previous:
                previous.stop()
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, bufsize=1,
                                       env={**os.environ, "DODGE_THREADS": "2"})
            lines = queue.Queue(maxsize=MAX_QUEUED_LINES)
            discard_output = threading.Event()
            def enqueue(item, preserve=False):
                while preserve or not discard_output.is_set():
                    try:
                        lines.put(item, timeout=0.1)
                        return True
                    except queue.Full:
                        if not preserve and discard_output.is_set():
                            return False
                return False

            def read_lines():
                try:
                    for line in process.stdout:
                        enqueue(line)
                finally:
                    enqueue(None, preserve=not discard_output.is_set())
                    process.stdout.close()
            reader = threading.Thread(target=read_lines, daemon=True,
                                      name=f"dodge-relay-reader-{process.pid}")
            reader.start()
            try:
                # The HNN model loads before metadata. Bound startup so an
                # abandoned or stalled request cannot retain a native process.
                deadline = time.monotonic() + START_TIMEOUT
                while True:
                    try:
                        line = lines.get(timeout=0.25)
                        break
                    except queue.Empty:
                        if process.poll() is not None:
                            raise RuntimeError("native stream exited before metadata")
                        if time.monotonic() >= deadline:
                            raise RuntimeError("native stream startup timed out")
                if line is None:
                    raise RuntimeError("native stream did not start")
                meta = json.loads(line).get("meta")
                if not isinstance(meta, dict):
                    raise RuntimeError("native stream returned invalid metadata")
            except (json.JSONDecodeError, RuntimeError) as error:
                discard_output.set()
                process.kill()
                process.wait(timeout=2)
                reader.join(timeout=2)
                raise RuntimeError("native stream startup failed or timed out") from error
            session = _Session(process, meta, lines, reader)
            session.discard_output = discard_output
            session.sid = secrets.token_urlsafe(12)
            with self._guard:
                self._session = session
            return {"sid": session.sid, "meta": meta}

    def next(self, query):
        count = self._integer(query, "n", 1, MAX_CHUNK, 60)
        with self._guard:
            session = self._session
        if not session or not secrets.compare_digest(query.get("sid", ""), session.sid):
            raise ValueError("unknown or expired run")
        session.touched = time.monotonic()
        frames = []
        with session.lock:
            stream = session.process.stdout
            while len(frames) < count and not session.ended and stream:
                try:
                    line = session.lines.get(timeout=READ_TIMEOUT)
                except queue.Empty:
                    session.ended = True
                    session.stop()
                    raise ValueError("native stream stalled and was stopped")
                if line is None:
                    session.ended = True
                    break
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise RuntimeError("native stream returned invalid JSON") from error
                if "result" in row:
                    session.result = row["result"]
                    session.ended = True
                    break
                frames.append(row)
                session.frames += 1
        return {"frames": frames, "ended": session.ended, "result": session.result}

    def stop(self, query):
        with self._guard:
            session = self._session
            if not session or not secrets.compare_digest(query.get("sid", ""), session.sid):
                raise ValueError("unknown or expired run")
            self._session = None
        session.stop()
        return {"stopped": True}

    def keepalive(self, query):
        with self._guard:
            session = self._session
            if not session or not secrets.compare_digest(query.get("sid", ""), session.sid):
                raise ValueError("unknown or expired run")
            with session.lock:
                if session.ended or time.monotonic() - session.touched > IDLE_SECONDS:
                    raise ValueError("unknown or expired run")
                session.touched = time.monotonic()
        return {"kept_alive": True}

    def _reap(self):
        while True:
            time.sleep(10)
            session = self._reap_idle()
            if session:
                session.stop()

    def _reap_idle(self):
        with self._guard:
            session = self._session
            if session and time.monotonic() - session.touched > IDLE_SECONDS:
                self._session = None
                return session
        return None
