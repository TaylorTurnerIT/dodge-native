"""Result-safety lifecycle for a separately registered future dispatcher.

No allocation or lease mutation exists here. The sole dispatcher supplies its
unchanged price, lease, control and total-time guards. Normal release requires
durable verified results. Financial/resource emergency release remains bounded
and explicitly reports data at risk instead of falsely reporting success.
"""
from pathlib import Path
import json
import sys
import time

from .custody import CHUNK_BYTES, canonical, digest, durable_new, identity, need

PREFLIGHT_BYTES = 32 * 1024**2


def schedule(jobs, updates):
    need(isinstance(jobs, tuple) and jobs and len(set(jobs)) == len(jobs), "Invalid job order")
    need(updates == (12, 24, 36), "Checkpoint exposure contract differs")
    result = [("preflight", None, 0)]
    for job in jobs:
        result.extend(("checkpoint", job, update) for update in updates)
        result.append(("job", job, 36))
    result.append(("terminal", None, 0))
    return tuple(result)


def stage_result(path, expected, *, returncode, directly_reaped, owned_group_absent, export=None):
    """Remote wrapper writes this after waiting on its real stage subprocess."""
    need(type(returncode) is int and type(directly_reaped) is bool
         and type(owned_group_absent) is bool, "Invalid stage process observation")
    body = dict(identity(expected), schema="dodge_remote_stage_exit_v1",
                observed_exit_code=returncode, directly_reaped=directly_reaped,
                owned_group_absent=owned_group_absent,
                status="complete" if returncode == 0 and directly_reaped and owned_group_absent
                and export is not None else "failed",
                terminal_export_sha256=None if export is None else export["sha256"],
                terminal_export_sequence=None if export is None else export["manifest"]["sequence"])
    durable_new(path, canonical(body))
    return body


class CheckpointGate:
    """Remote worker barrier: a checkpoint is not a backup until parent ack."""
    def __init__(self, publisher, jobs, *, guard, ack_seconds):
        self.publisher, self.jobs = publisher, jobs
        self.steps = schedule(jobs, (12, 24, 36))
        self.guard, self.ack_seconds = guard, ack_seconds

    def preflight(self, challenge):
        need(Path(challenge).stat().st_size == PREFLIGHT_BYTES, "Full-size transfer rehearsal required")
        export = self.publisher.publish(1, "preflight", {"roundtrip.bin": challenge})
        self.publisher.wait_for_ack(export, guard=self.guard, seconds=self.ack_seconds)
        return export

    def wrap_factory(self, factory, preflight_export):
        def create(reg, job, out, guard):
            # This barrier runs BEFORE the actual session/native constructor.
            self.publisher.wait_for_ack(preflight_export, guard=guard, seconds=self.ack_seconds)
            session = factory(reg, job, out, guard)
            gate = self

            class SessionWithBackup:
                def __getattr__(self, name):
                    return getattr(session, name)

                def checkpoint(self, path, update):
                    descriptor = session.checkpoint(path, update)
                    index = gate.steps.index(("checkpoint", job["id"], update)) + 1
                    descriptor_path = Path(out) / ("checkpoint-%03d-descriptor.json" % update)
                    durable_new(descriptor_path, canonical(descriptor))
                    export = gate.publisher.publish(index, "checkpoint", {
                        "checkpoint.pt": Path(path), "checkpoint-descriptor.json": descriptor_path,
                        "updates.jsonl": Path(out) / "updates.jsonl",
                    }, job=job["id"], update=update)
                    gate.publisher.wait_for_ack(export, guard=guard, seconds=gate.ack_seconds)
                    return descriptor

            return SessionWithBackup()
        return create

    def job_complete(self, job, files):
        # Call after the supervisor has reaped the worker and written its result.
        sequence = self.steps.index(("job", job, 36)) + 1
        need({"worker-result.json", "supervisor-result.json"} <= set(files), "Job exit receipts absent")
        export = self.publisher.publish(sequence, "job", files, job=job, update=36)
        self.publisher.wait_for_ack(export, guard=self.guard, seconds=self.ack_seconds)
        return export


class StageController:
    """Parent coordinator component; all exceptions stop further work grants."""
    def __init__(self, receiver, *, jobs, challenge_sha256, endpoint, guard,
                 cancel_work, verify_owned_endpoint, release_owned_endpoint,
                 validate_boundary, validate_terminal, emergency_authorized):
        self.receiver, self.expected = receiver, receiver.expected
        self.steps = schedule(jobs, (12, 24, 36))
        self.challenge_sha256, self.endpoint = challenge_sha256, endpoint
        self.guard, self.cancel_work = guard, cancel_work
        self.verify_owned_endpoint = verify_owned_endpoint
        self.release_owned_endpoint = release_owned_endpoint
        self.validate_terminal = validate_terminal
        self.validate_boundary = validate_boundary
        self.emergency_authorized = emergency_authorized
        self.next_sequence = 1
        self.training_started = False
        self.failed = False
        self.terminal_verified = False
        self.release_consumed = False

    def fail(self, phase, error):
        self.failed = True
        path = self.receiver.root / "first-failure.json"
        try:
            if not path.exists():
                body = dict(self.expected, schema="dodge_result_safety_failure_v1", phase=phase,
                            exception_type=type(error).__name__, campaign_success=False)
                # TransportError deliberately exposes only these safe fields.
                for key in ("operation", "http_status", "failure_class"):
                    if hasattr(error, key):
                        body[key] = getattr(error, key)
                durable_new(path, canonical(body))
        finally:
            self.cancel_work()

    def sync(self, pointer):
        need(not self.failed, "Result-safety failure is permanent")
        try:
            self.guard()
            need(pointer["sequence"] == self.next_sequence <= len(self.steps), "Export skipped or replayed")
            # Validate kind/boundary before Receiver sends an acknowledgment.
            raw = self.receiver.get_json("manifests/%06d.json" % self.next_sequence)
            need(digest(raw) == pointer["sha256"], "Pointer digest differs")
            body = json.loads(raw)
            expected_step = self.steps[self.next_sequence - 1]
            need((body.get("kind"), body.get("job"), body.get("update")) == expected_step,
                 "Export boundary differs")
            if self.next_sequence == 1:
                sample = body.get("members", {}).get("roundtrip.bin", {})
                need(sample.get("bytes") == PREFLIGHT_BYTES
                     and sample.get("sha256") == self.challenge_sha256
                     and len(set(sample.get("chunks", []))) == (PREFLIGHT_BYTES + CHUNK_BYTES - 1) // CHUNK_BYTES,
                     "Transfer rehearsal challenge differs")
            def validate_boundary(manifest, files):
                if manifest["kind"] in ("checkpoint", "job"):
                    self.validate_boundary(files, kind=manifest["kind"], job=manifest["job"],
                                           update=manifest["update"], allow_fixtures=False)
            receipt = self.receiver.mirror(pointer, before_ack=validate_boundary)
            self.next_sequence += 1
            return receipt
        except BaseException as error:
            self.fail("incremental_backup", error)
            raise

    def start_training(self, start):
        """Exactly one start, after a real full-size roundtrip and local readback."""
        need(not self.failed and not self.training_started and self.next_sequence == 2,
             "Training blocked: transfer rehearsal missing or start already consumed")
        self.guard()
        body, _ = self.receiver.verify(1)
        need(body["members"]["roundtrip.bin"]["sha256"] == self.challenge_sha256,
             "Transfer rehearsal changed")
        durable_new(self.receiver.root / "training-start.claimed", canonical(self.expected))
        self.training_started = True
        try:
            return start()
        except BaseException as error:
            self.fail("stage_start", error)
            raise

    def finish(self, cli_exit_code, stage_exit_bytes):
        """A successful CLI process is insufficient, even if it displayed errors."""
        try:
            self.guard()
            need(not self.failed and self.training_started, "Stage not admitted")
            need(cli_exit_code == 0 and stage_exit_bytes is not None, "Remote stage receipt absent")
            stage = json.loads(stage_exit_bytes)
            need(stage.get("schema") == "dodge_remote_stage_exit_v1" and identity(stage) == self.expected
                 and stage.get("status") == "complete" and stage.get("observed_exit_code") == 0
                 and type(stage["observed_exit_code"]) is int and stage.get("directly_reaped") is True
                 and stage.get("owned_group_absent") is True,
                 "Remote stage failed or exit proof differs")
            need(self.next_sequence == len(self.steps) + 1, "Required checkpoint/job/terminal backups missing")
            body, files = self.receiver.verify(len(self.steps))
            need("training-artifacts.tar" in body["members"]
                 and body["members"]["training-artifacts.tar"]["bytes"] > 0,
                 "Complete terminal archive absent")
            manifest_bytes = canonical(body)
            need(stage["terminal_export_sequence"] == len(self.steps)
                 and stage["terminal_export_sha256"] == digest(manifest_bytes), "Stage/terminal binding differs")
            # Existing strict owner decoder and full lifecycle checks remain mandatory.
            verdict = self.validate_terminal(files, allow_fixtures=False)
            need(verdict.get("status") == "complete_archive_verified", "Strict terminal validation failed")
            durable_new(self.receiver.root / "remote-stage-exit.json", stage_exit_bytes)
            durable_new(self.receiver.root / "terminal-backup-verified.json",
                        canonical(dict(self.expected, status="strict_terminal_backup_verified",
                                       terminal_manifest_sha256=digest(manifest_bytes),
                                       stage_exit_sha256=digest(stage_exit_bytes),
                                       required_exports=len(self.steps), campaign_accepted=False)))
            self.terminal_verified = True
        except BaseException as error:
            self.fail("terminal_validation", error)
            raise

    def normal_release(self):
        need(not self.failed and self.terminal_verified and not self.release_consumed,
             "Normal VM release blocked: durable terminal results absent")
        try:
            return self._normal_release()
        except BaseException as error:
            self.fail("normal_release", error)
            raise

    def _normal_release(self):
        self.guard()
        self.verify_owned_endpoint(self.endpoint)
        audit = json.loads((self.receiver.root / "terminal-backup-verified.json").read_bytes())
        need(identity(audit) == self.expected and audit["status"] == "strict_terminal_backup_verified"
             and audit["stage_exit_sha256"] == digest((self.receiver.root / "remote-stage-exit.json").read_bytes()),
             "Durable terminal proof absent or changed")
        # Revalidate all saved boundaries immediately before the irreversible action.
        for sequence in range(1, len(self.steps) + 1):
            self.receiver.verify(sequence)
        durable_new(self.receiver.root / "normal-release-permit.json",
                    canonical(dict(self.expected, endpoint=self.endpoint,
                                   status="all_required_results_durable_before_VM_release")))
        self.release_consumed = True
        return self.release_owned_endpoint(self.endpoint)

    def emergency_release(self, reason):
        """Honor finite financial/resource bounds; never quietly waive result loss."""
        need(reason in ("financial_cap", "resource_cap", "lease_lost", "provider_unreachable"),
             "Unknown emergency release reason")
        need(not self.release_consumed and self.emergency_authorized(reason),
             "Emergency release not authorized by registered safety guard")
        self.cancel_work()
        self.verify_owned_endpoint(self.endpoint)
        backed_up, unverified = [], []
        for sequence, boundary in enumerate(self.steps, 1):
            try:
                self.receiver.verify(sequence)
                backed_up.append(dict(sequence=sequence, boundary=boundary))
            except (OSError, ValueError, KeyError):
                unverified.append(dict(sequence=sequence, boundary=boundary))
        report = dict(self.expected, endpoint=self.endpoint, reason=reason,
                      campaign_success=False, backed_up=backed_up, unverified=unverified,
                      status="safety_release_with_explicit_result_risk")
        try:
            durable_new(self.receiver.root / "emergency-release-data-at-risk.json", canonical(report))
        except OSError as error:
            # A broken destination must not turn a finite financial cap into
            # an indefinitely paid VM. Report the missing audit explicitly.
            self.emergency_audit_error = type(error).__name__
            sys.stderr.write(canonical(dict(record=self.expected["record"], reason=reason,
                             status="emergency_audit_not_durable", campaign_success=False,
                             exception_type=type(error).__name__)).decode())
        self.failed = True
        self.release_consumed = True
        return self.release_owned_endpoint(self.endpoint)

    def wait_stage(self, process, *, next_pointer, read_stage_exit, pause=time.sleep):
        """Poll exports while kernel is busy; never execute another notebook cell."""
        try:
            while process.poll() is None:
                self.guard()
                if self.next_sequence <= len(self.steps):
                    pointer = next_pointer(self.next_sequence)
                    if pointer is not None:
                        self.sync(pointer)
                pause(.1)
            code = process.wait()
            # Drain exports produced just before the stage exited.
            while self.next_sequence <= len(self.steps):
                pointer = next_pointer(self.next_sequence)
                if pointer is None:
                    break
                self.sync(pointer)
            self.finish(code, read_stage_exit())
        except BaseException as error:
            self.fail("stage_wait", error)
            raise
