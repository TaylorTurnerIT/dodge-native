"""Real disk/HTTP/subprocess fault fixtures; no account calls, model or games."""
import base64
from contextlib import contextmanager
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.experiments.teacher_colab_result_safety_20261031_r1 import custody as c
from learning.experiments.teacher_colab_result_safety_20261031_r1 import lifecycle as life
from learning.experiments.teacher_colab_result_safety_20261031_r1 import remote_stage
from learning.experiments.teacher_colab_result_safety_20261031_r1 import transport as wire

IDENTITY = dict(record="DODGE-063", job_nonce="f7801cc7-b783-4aa2-a718-1a0b8a616d5f",
                registration_sha256="a" * 64, expected_lease_sha256="b" * 64)


class LocalWire:
    def __init__(self, root):
        self.root, self.acks = Path(root), []
        self.fail_chunk = None

    def get_json(self, name):
        return (self.root / name).read_bytes()

    def get_chunk(self, name):
        if self.fail_chunk is not None:
            raise self.fail_chunk
        return (self.root / name).read_bytes()

    def put_ack(self, name, data):
        c.durable_new(self.root / name, data)
        self.acks.append((name, data))


class SafetyFixture:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.pub = c.Publisher(self.root / "remote", IDENTITY)
        self.wire = LocalWire(self.pub.root)
        self.receiver = c.Receiver(self.root / "off-vm", IDENTITY,
                                   get_json=self.wire.get_json, get_chunk=self.wire.get_chunk,
                                   put_ack=self.wire.put_ack, guard=lambda: None)
        self.sample = self.root / "roundtrip.bin"
        self.sample.write_bytes(os.urandom(life.PREFLIGHT_BYTES))
        self.cancel = Mock()
        self.release = Mock(return_value={"assignment_absence_confirmed": True})
        self.owned = Mock()
        self.decoder = Mock(return_value={"status": "complete_archive_verified"})
        self.boundary_decoder = Mock()
        self.controller = life.StageController(self.receiver, jobs=("r1-control",),
                    challenge_sha256=c.file_digest(self.sample), endpoint="exact-owned-fixture",
                    guard=lambda: None, cancel_work=self.cancel, verify_owned_endpoint=self.owned,
                    release_owned_endpoint=self.release, validate_terminal=self.decoder,
                    validate_boundary=self.boundary_decoder,
                    emergency_authorized=lambda reason: reason == "financial_cap")

    def export(self, sequence, kind, files=None, job=None, update=0):
        if files is None:
            source = self.root / ("data-%06d" % sequence)
            source.write_bytes(("CPU-fixture-" + str(sequence)).encode())
            filename = "checkpoint.pt" if kind == "checkpoint" else (
                "training-artifacts.tar" if kind == "terminal" else "receipt.json")
            files = {filename: source}
        export = self.pub.publish(sequence, kind, files, job=job, update=update)
        self.controller.sync(dict(sequence=sequence, sha256=export["sha256"]))
        return export

    def preflight(self):
        return self.export(1, "preflight", {"roundtrip.bin": self.sample})

    def full_stage(self):
        self.preflight()
        self.controller.start_training(lambda: None)
        for sequence, (kind, job, update) in enumerate(self.controller.steps[1:], 2):
            export = self.export(sequence, kind, job=job, update=update)
        stage = life.stage_result(self.pub.root / "stage-exit.json", IDENTITY,
                                 returncode=0, directly_reaped=True, owned_group_absent=True, export=export)
        self.controller.finish(0, c.canonical(stage))
        return export


class CustodyFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Small unit fixtures cannot qualify production's fixed 32 MiB gate.
        self.small = patch.object(life, "PREFLIGHT_BYTES", 65536)
        self.small.start()
        self.addCleanup(self.small.stop)
        self.addCleanup(self.temp.cleanup)
        self.f = SafetyFixture(self.temp.name)

    def tearDown(self):
        self.small.stop()
        self.temp.cleanup()

    def test_training_never_starts_before_roundtrip(self):
        start = Mock()
        with self.assertRaisesRegex(ValueError, "Training blocked"):
            self.f.controller.start_training(start)
        start.assert_not_called()
        self.f.preflight()
        self.f.controller.start_training(start)
        start.assert_called_once()
        with self.assertRaisesRegex(ValueError, "already consumed"):
            self.f.controller.start_training(start)

    def test_rehearsal_requires_exact_challenge_and_size_before_ack(self):
        self.f.controller.challenge_sha256 = "f" * 64
        with self.assertRaisesRegex(ValueError, "challenge differs"):
            self.f.preflight()
        self.assertEqual(self.f.wire.acks, [])
        self.f.cancel.assert_called()

    def test_wrong_nonce_rejected_and_no_ack(self):
        self.f.pub.expected["job_nonce"] = "ffe35413-316b-45a2-b487-53fa564f9841"
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.f.preflight()
        self.assertEqual(self.f.wire.acks, [])

    def test_truncated_chunk_preserves_prior_checkpoint(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        self.f.export(2, "checkpoint", job="r1-control", update=12)
        prior = self.f.receiver.verify(2)[0]
        self.f.receiver.get_chunk = lambda _: b""
        with self.assertRaisesRegex(ValueError, "chunk differs"):
            self.f.export(3, "checkpoint", job="r1-control", update=24)
        self.assertEqual(self.f.receiver.verify(2)[0], prior)
        self.assertTrue((self.f.receiver.exports / "000003/first-failure.json").exists())
        self.assertTrue(list((self.f.receiver.exports / "000003/files").glob("*.partial")))
        self.assertEqual(len(self.f.wire.acks), 2)
        with self.assertRaisesRegex(ValueError, "Normal VM release blocked"):
            self.f.controller.normal_release()
        self.f.release.assert_not_called()

    def test_disk_fsync_failure_never_acknowledges(self):
        export = self.f.pub.publish(1, "preflight", {"roundtrip.bin": self.f.sample})
        with patch.object(c.os, "fsync", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                self.f.controller.sync(dict(sequence=1, sha256=export["sha256"]))
        self.assertEqual(self.f.wire.acks, [])
        self.f.cancel.assert_called()

    def test_ack_written_after_receipt_and_durable_readback(self):
        def ack(name, data):
            self.f.receiver.verify(1)
            self.assertTrue((self.f.receiver.exports / "000001/backup-receipt.json").exists())
            self.f.wire.put_ack(name, data)
        self.f.receiver.put_ack = ack
        export = self.f.preflight()
        self.f.pub.wait_for_ack(export, guard=lambda: None, seconds=1)

    def test_ack_loss_keeps_verified_copy_and_blocks_more_work(self):
        self.f.receiver.put_ack = Mock(side_effect=wire.TransportError("acknowledge", "connection_error"))
        with self.assertRaises(wire.TransportError):
            self.f.preflight()
        self.assertTrue((self.f.receiver.exports / "000001/backup-receipt.json").exists())
        self.assertTrue((self.f.receiver.exports / "000001/first-failure.json").exists())
        self.assertEqual(self.f.controller.next_sequence, 1)

    def test_bad_ack_rejected(self):
        export = self.f.pub.publish(1, "preflight", {"roundtrip.bin": self.f.sample})
        c.durable_new(self.f.pub.acks / "000001.json", c.canonical(dict(IDENTITY,
                     schema="dodge_result_backup_ack_v1", sequence=1, manifest_sha256="f" * 64,
                     status="durable_copy_readback_verified")))
        with self.assertRaisesRegex(ValueError, "acknowledgment differs"):
            self.f.pub.wait_for_ack(export, guard=lambda: None, seconds=1)

    def test_missing_ack_reaches_deadline_without_continuing(self):
        export = self.f.pub.publish(1, "preflight", {"roundtrip.bin": self.f.sample})
        clock = iter([0, 0, 2])
        with self.assertRaisesRegex(ValueError, "acknowledgment deadline"):
            self.f.pub.wait_for_ack(export, guard=lambda: None, seconds=1,
                                   clock=lambda: next(clock), pause=lambda _: None)

    def test_boundary_replay_or_skip_fails_before_ack(self):
        self.f.preflight()
        export = self.f.pub.publish(3, "checkpoint", {"checkpoint.pt": self.f.sample},
                                    job="r1-control", update=24)
        with self.assertRaisesRegex(ValueError, "skipped or replayed"):
            self.f.controller.sync(dict(sequence=3, sha256=export["sha256"]))
        self.assertEqual(len(self.f.wire.acks), 1)

    def test_cli_exit0_without_stage_receipt_is_failure(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        with self.assertRaisesRegex(ValueError, "receipt absent"):
            self.f.controller.finish(0, None)
        self.f.cancel.assert_called()
        self.f.release.assert_not_called()

    def test_remote_failure_cannot_be_overridden_by_cli_exit0(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        stage = life.stage_result(self.f.pub.root / "stage-exit.json", IDENTITY,
                                 returncode=1, directly_reaped=True, owned_group_absent=True)
        with self.assertRaisesRegex(ValueError, "Remote stage failed"):
            self.f.controller.finish(0, c.canonical(stage))

    def test_success_cannot_skip_checkpoint_or_job_receipts(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        export = self.f.pub.publish(6, "terminal", {"receipt.json": self.f.sample})
        stage = life.stage_result(self.f.pub.root / "stage-exit.json", IDENTITY,
                                 returncode=0, directly_reaped=True, owned_group_absent=True, export=export)
        with self.assertRaisesRegex(ValueError, "backups missing"):
            self.f.controller.finish(0, c.canonical(stage))

    def test_release_requires_production_decoder_and_durable_permit_first(self):
        self.f.full_stage()
        self.f.decoder.assert_called_once()
        self.assertIs(self.f.decoder.call_args.kwargs["allow_fixtures"], False)
        def release(endpoint):
            self.assertEqual(endpoint, "exact-owned-fixture")
            self.assertTrue((self.f.receiver.root / "normal-release-permit.json").exists())
            self.assertTrue((self.f.receiver.root / "terminal-backup-verified.json").exists())
        self.f.controller.release_owned_endpoint = release
        self.f.controller.normal_release()
        with self.assertRaisesRegex(ValueError, "Normal VM release blocked"):
            self.f.controller.normal_release()

    def test_tampered_backup_blocks_release(self):
        self.f.full_stage()
        (self.f.receiver.exports / "000002/files/checkpoint.pt").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "absent or changed"):
            self.f.controller.normal_release()
        self.f.release.assert_not_called()

    def test_failing_strict_decoder_never_grants_release(self):
        self.f.decoder.side_effect = ValueError("strict checkpoint verification failed")
        with self.assertRaisesRegex(ValueError, "strict checkpoint"):
            self.f.full_stage()
        self.f.release.assert_not_called()
        self.assertFalse(self.f.controller.terminal_verified)

    def test_bad_boundary_receipt_never_acknowledges_or_opens_next_job(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        self.f.boundary_decoder.side_effect = ValueError("checkpoint or journal differs")
        with self.assertRaisesRegex(ValueError, "journal differs"):
            self.f.export(2, "checkpoint", job="r1-control", update=12)
        self.assertEqual(len(self.f.wire.acks), 1)
        self.assertIs(self.f.boundary_decoder.call_args.kwargs["allow_fixtures"], False)

    def test_emergency_release_records_exact_recovered_boundaries_first(self):
        self.f.preflight()
        self.f.controller.start_training(lambda: None)
        self.f.export(2, "checkpoint", job="r1-control", update=12)
        def release(endpoint):
            report = json.loads((self.f.receiver.root / "emergency-release-data-at-risk.json").read_bytes())
            self.assertEqual(report["endpoint"], endpoint)
            self.assertFalse(report["campaign_success"])
            self.assertEqual([x["sequence"] for x in report["backed_up"]], [1, 2])
            self.assertEqual(len(report["unverified"]), 4)
        self.f.controller.release_owned_endpoint = release
        self.f.controller.emergency_release("financial_cap")
        self.f.cancel.assert_called()

    def test_emergency_never_waives_budget_guard_or_ownership(self):
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.f.controller.emergency_release("resource_cap")
        self.f.release.assert_not_called()
        self.f.controller.verify_owned_endpoint = Mock(side_effect=ValueError("ownership unknown"))
        with self.assertRaisesRegex(ValueError, "ownership unknown"):
            self.f.controller.emergency_release("financial_cap")
        self.f.release.assert_not_called()

    def test_broken_audit_disk_cannot_extend_financial_cap(self):
        with patch.object(life, "durable_new", side_effect=OSError("disk full")), patch.object(sys, "stderr", io.StringIO()) as stderr:
            self.f.controller.emergency_release("financial_cap")
        self.f.release.assert_called_once_with("exact-owned-fixture")
        self.assertFalse(self.f.controller.terminal_verified)
        self.assertIn("emergency_audit_not_durable", stderr.getvalue())

    def test_safe_error_metadata_preserved_without_private_message(self):
        self.f.receiver.get_chunk = Mock(side_effect=wire.TransportError("read", "http_status", 503))
        with self.assertRaises(wire.TransportError):
            self.f.preflight()
        body = json.loads((self.f.receiver.root / "first-failure.json").read_bytes())
        self.assertEqual(body["http_status"], 503)
        self.assertEqual(body["operation"], "read")
        self.assertNotIn("url", body)
        self.assertNotIn("token", body)

    def test_first_failure_cannot_be_overwritten(self):
        self.f.controller.fail("first", ValueError("private URL must never escape"))
        path = self.f.receiver.root / "first-failure.json"
        before = path.read_bytes()
        self.f.controller.fail("second", TimeoutError())
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn(b"private URL", before)

    def test_manifest_traversal_and_empty_inventory_rejected(self):
        for name in ("../escape.pt", "/absolute", "a//b", "a/../b", "a\\b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                c.relative_name(name)
        with self.assertRaisesRegex(ValueError, "Invalid export inventory"):
            c.validate_manifest(dict(IDENTITY, schema="dodge_result_export_v1", sequence=1,
                                kind="terminal", job=None, update=0, members={}), IDENTITY)

    def test_symlink_destination_rejected(self):
        alias = self.f.root / "alias"
        alias.symlink_to(self.f.receiver.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Redirected"):
            c.real_directory(alias)


@contextmanager
def contents_server(root, *, status=None, corrupt=False, delay=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if delay:
                time.sleep(delay)
            if status is not None:
                self.send_response(status); self.end_headers(); return
            relative = unquote(urlsplit(self.path).path).split("/exports/", 1)[1]
            path = Path(root) / relative
            if not path.is_file():
                self.send_response(404); self.end_headers(); return
            data = b"wrong-data" if corrupt else path.read_bytes()
            encoded = json.dumps(dict(type="file", format="base64", content=base64.b64encode(data).decode())).encode()
            self.send_response(200); self.end_headers()
            try:
                self.wfile.write(encoded)
            except BrokenPipeError:
                pass

        def do_PUT(self):
            relative = unquote(urlsplit(self.path).path).split("/exports/", 1)[1]
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert "chunk" not in payload
            c.durable_new(Path(root) / relative, payload["content"].encode())
            self.send_response(201); self.end_headers(); self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%s" % server.server_port
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


class RealBoundaryTests(unittest.TestCase):
    def transport(self, url):
        return wire.ContentsTransport(session_provider=lambda: SimpleNamespace(url=url, token="PRIVATE_FIXTURE_TOKEN", endpoint="owned"),
                    endpoint="owned", remote_root="/content/fixture/exports", verify_owned_endpoint=lambda _: None,
                    guard=lambda: None, fixture_only=True)

    def test_real_32MiB_roundtrip_disk_HTTP_process_ack_then_release(self):
        self.assertEqual(life.PREFLIGHT_BYTES, 32 * 1024**2)
        with tempfile.TemporaryDirectory() as directory:
            f = SafetyFixture(directory)
            with contents_server(f.pub.root) as url:
                client = self.transport(url)
                f.receiver.get_json = client.get_json
                f.receiver.get_chunk = client.get_chunk
                f.receiver.put_ack = client.put_ack
                f.full_stage()
                f.controller.normal_release()
                f.release.assert_called_once_with("exact-owned-fixture")
                self.assertEqual(len(list(f.receiver.objects.glob("*.bin"))), 37)

    def test_HTTP_error_status_retained_without_secret_URL(self):
        with tempfile.TemporaryDirectory() as directory, contents_server(directory, status=503) as url:
            with self.assertRaises(wire.TransportError) as caught:
                self.transport(url).get_json("stage-exit.json")
            self.assertEqual(caught.exception.http_status, 503)
            self.assertNotIn("PRIVATE_FIXTURE_TOKEN", str(caught.exception))
            self.assertNotIn(url, str(caught.exception))

    def test_redirect_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory, contents_server(directory, status=302) as url:
            with self.assertRaises(wire.TransportError) as caught:
                self.transport(url).get_json("stage-exit.json")
            self.assertEqual(caught.exception.http_status, 302)

    def test_404_optional_readiness_is_distinct_from_lost_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory, contents_server(directory) as url:
            client = self.transport(url)
            self.assertIsNone(client.next_pointer(1))
            with self.assertRaises(wire.TransportError) as caught:
                client.get_chunk("chunks/" + "a" * 64 + ".bin")
            self.assertEqual(caught.exception.http_status, 404)

    def test_total_deadline_kills_and_reaps_transfer_subprocess(self):
        with tempfile.TemporaryDirectory() as directory, contents_server(directory, delay=.5) as url:
            real_popen = subprocess.Popen
            children = []
            def spawn(*args, **kwargs):
                child = real_popen(*args, **kwargs); children.append(child); return child
            with patch.object(wire, "REQUEST_SECONDS", .05), patch.object(wire.subprocess, "Popen", side_effect=spawn):
                with self.assertRaises(wire.TransportError) as caught:
                    self.transport(url).get_json("stage-exit.json")
            self.assertEqual(caught.exception.failure_class, "total_deadline")
            self.assertIsNotNone(children[0].returncode)

    def test_transfer_path_allowlist_prohibits_control_and_heldout_reads(self):
        client = self.transport("http://127.0.0.1:1")
        for path in ("../control.json", "control.json", "inputs/D13.json", "chunks/no-hash.bin"):
            with self.subTest(path=path), self.assertRaises(wire.TransportError):
                client.get_json(path)

    def test_no_HTTP_in_production(self):
        client = self.transport("http://127.0.0.1:1")
        client.fixture_only = False
        with self.assertRaises(wire.TransportError) as caught:
            client.read_stage_exit()
        self.assertEqual(caught.exception.failure_class, "response_format")

    def test_each_transfer_uses_current_session_and_rechecks_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, contents_server(directory) as url:
            client = self.transport(url)
            provider = Mock(return_value=SimpleNamespace(url=url, token="ROTATED_FIXTURE", endpoint="owned"))
            client.session_provider = provider
            self.assertIsNone(client.read_stage_exit())
            provider.assert_called_once()
            provider.return_value.endpoint = "unowned"
            with self.assertRaises(wire.TransportError) as caught:
                client.read_stage_exit()
            self.assertEqual(caught.exception.failure_class, "identity_mismatch")

    def test_real_remote_child_nonzero_produces_failed_exit_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            result = remote_stage.run_stage_child([sys.executable, "-B", "-c", "raise SystemExit(7)"],
                    Path(directory).resolve(), IDENTITY, guard=lambda: None, seconds=2, terminal_export=Mock())
            self.assertEqual(result["observed_exit_code"], 7)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["directly_reaped"])
            self.assertTrue(result["owned_group_absent"])
            self.assertTrue((Path(directory) / "stage-first-failure.json").exists())

    def test_real_remote_child_timeout_is_reaped_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            result = remote_stage.run_stage_child([sys.executable, "-B", "-c", "import time;time.sleep(10)"],
                    Path(directory).resolve(), IDENTITY, guard=lambda: None, seconds=.05, terminal_export=Mock())
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["owned_group_absent"])
            with self.assertRaisesRegex(ValueError, "already exists"):
                remote_stage.run_stage_child([sys.executable, "-B", "-c", "pass"],
                    Path(directory).resolve(), IDENTITY, guard=lambda: None, seconds=1, terminal_export=Mock())

    def test_missing_ack_blocks_actual_checkpoint_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(life, "PREFLIGHT_BYTES", 65536):
            f = SafetyFixture(directory)
            gate = life.CheckpointGate(f.pub, ("r1-control",), guard=lambda: None, ack_seconds=.15)
            export = f.preflight()
            out = f.root / "worker"; out.mkdir(); (out / "updates.jsonl").write_text('{"update":12}\n')
            class Session:
                def checkpoint(self, path, update):
                    Path(path).write_bytes(b"CPU-fixture-weights")
                    return dict(update=update, sha256=c.file_digest(path))
            factory = gate.wrap_factory(lambda *_: Session(), export)
            session = factory({}, {"id": "r1-control"}, out, lambda: None)
            reached_next_update = []
            with self.assertRaisesRegex(ValueError, "acknowledgment deadline"):
                session.checkpoint(out / "checkpoint-012.pt", 12)
                reached_next_update.append(True)
            self.assertEqual(reached_next_update, [])
            self.assertTrue((out / "checkpoint-012.pt").exists())

    def test_native_constructor_never_runs_without_preflight_ack(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(life, "PREFLIGHT_BYTES", 65536):
            f = SafetyFixture(directory)
            export = f.pub.publish(1, "preflight", {"roundtrip.bin": f.sample})
            gate = life.CheckpointGate(f.pub, ("r1-control",), guard=lambda: None, ack_seconds=.01)
            constructor = Mock()
            factory = gate.wrap_factory(constructor, export)
            with self.assertRaisesRegex(ValueError, "acknowledgment deadline"):
                factory({}, {"id": "r1-control"}, f.root, lambda: None)
            constructor.assert_not_called()

    def test_real_worker_checkpoint_hook_propagates_backup_failure(self):
        source = ROOT / "learning/experiments/teacher_ray_colab_training_r2"
        sys.path.insert(0, str(source))
        import common as old_common
        spec = importlib.util.spec_from_file_location("result_safety_real_old_worker", source / "worker.py")
        old_worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(old_worker)
        with tempfile.TemporaryDirectory() as directory, patch.object(life, "PREFLIGHT_BYTES", 65536):
            f = SafetyFixture(directory)
            export = f.preflight()
            gate = life.CheckpointGate(f.pub, ("r1-control",), guard=lambda: None, ack_seconds=.05)
            out = f.root / "real-worker"; out.mkdir()
            updates = []
            class Session:
                fixture_only = True
                stream_digest = "CPU-fixture-no-pool"
                def __init__(self, *_): pass
                def resources(self): return dict(peak_rss_bytes=1, peak_cuda_reserved_bytes=0)
                def step(self, update, guard):
                    updates.append(update)
                    with (out / "updates.jsonl").open("a") as stream:
                        stream.write(json.dumps(dict(kind="update_complete", local_update=update)) + "\n")
                    return dict(training_frames=update, completed_updates=update, passive_GAE_return_identity=True)
                def checkpoint(self, path, update):
                    Path(path).write_bytes(b"CPU-fixture-checkpoint")
                    return dict(update=update, sha256=c.file_digest(path))
                def counts(self): return dict(training_frames=len(updates), completed_updates=len(updates), native_games=0)
                def close(self): pass
                def failure(self, error): return {}
            reg = dict(IDENTITY, payload_sha256="c" * 64, work_seconds=5, campaign_total_seconds=10,
                       campaign_started_monotonic=time.monotonic(), jobs=[dict(id="r1-control")],
                       updates=36, envs=1, rollout=1, prefix_updates=2, IO_reserve_seconds=0,
                       receipt_seconds=.1, checkpoint_updates=[12, 24, 36], frame_target=36)
            result = old_worker.run_trajectory(reg, reg["jobs"][0], out,
                        session_factory=gate.wrap_factory(Session, export))
            self.assertEqual(updates, list(range(1, 13)))
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["completed_updates"], 12)
            self.assertTrue((out / "worker-first-failure.json").exists())
        sys.path.remove(str(source))

    def test_parent_wait_stage_drains_final_exports_and_real_process(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(life, "PREFLIGHT_BYTES", 65536):
            f = SafetyFixture(directory)
            f.preflight()
            child = f.controller.start_training(lambda: subprocess.Popen(
                [sys.executable, "-B", "-c", "pass"]))
            export = None
            for sequence, (kind, job, update) in enumerate(f.controller.steps[1:], 2):
                path = f.root / ("fixture-data-%d" % sequence); path.write_bytes(b"CPU-fixture")
                name = "checkpoint.pt" if kind == "checkpoint" else (
                    "training-artifacts.tar" if kind == "terminal" else "receipt.json")
                export = f.pub.publish(sequence, kind, {name: path}, job=job, update=update)
            stage = life.stage_result(f.pub.root / "stage-exit.json", IDENTITY, returncode=0,
                                      directly_reaped=True, owned_group_absent=True, export=export)
            f.controller.wait_stage(child,
                next_pointer=lambda seq: json.loads((f.pub.ready / ("%06d.json" % seq)).read_bytes()),
                read_stage_exit=lambda: c.canonical(stage))
            self.assertEqual(child.returncode, 0)
            self.assertTrue(f.controller.terminal_verified)
            f.controller.normal_release()
            f.release.assert_called_once()


class OfficialCLIRegressionTests(unittest.TestCase):
    def test_installed_CLI_returns_normally_for_remote_error_outputs(self):
        # Exercise official installed exec_command itself, with no account/client.
        sdk = Path('/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')
        self.assertTrue(sdk.is_dir(), "Registered local SDK absent; do not silently skip")
        sys.path.insert(0, str(sdk))
        import colab_cli.common as common
        from colab_cli.commands import execution
        session = SimpleNamespace(url='https://offline.invalid', token='PRIVATE_FIXTURE_TOKEN',
                                  kernel_id=None, session_id=None)
        state = SimpleNamespace(resolve_session=lambda _: 'fixture', get_session=lambda _: session,
                                store=SimpleNamespace(add=Mock()), history=SimpleNamespace(log_event=Mock()))
        runtime = Mock()
        runtime.execute_code.return_value = [dict(output_type='error', ename='RuntimeError', evalue='fixture failure')]
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'fixture.py'; script.write_text('raise RuntimeError("fixture failure")')
            with patch.object(common, 'state', state), patch.object(execution, 'ColabRuntime', return_value=runtime):
                self.assertIsNone(execution.exec_command(session='fixture', file=str(script),
                                                        output_image=None, timeout=1, env=[]))
        runtime.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
