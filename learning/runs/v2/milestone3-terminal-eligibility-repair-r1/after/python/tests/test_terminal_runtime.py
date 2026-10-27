"""Synthetic lease, launch, worker-bypass and late-finalization controls."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import inspect
import io
import json
import os
import signal
from types import SimpleNamespace

import pytest
import torch

from dodge_rl import checkpoints as c, identity as i, supervision as s, train_teacher as t
from test_runtime_repair import NoopGuard, runner_args, mock_authorization
from test_terminal_eligibility import _source, transition


def lease_for(args, phase, anchor=None):
    value = {"kind": "M3_teacher", "authorization": "frozen_reviewed_M3_teacher",
             "run_id": args.run_id, "phase": phase,
             "identity_sha256": i.file_hash(args.identity), "config_sha256": i.file_hash(args.config)}
    if anchor is not None:
        value["parent_terminal_receipt"] = copy.deepcopy(anchor)
    return value


def bind_state(monkeypatch, path):
    actual = s.assert_lease
    parameters = inspect.signature(actual).parameters
    def bound(run_id, identity_sha256, config_sha256, *args, **kwargs):
        return actual(run_id, identity_sha256, config_sha256, path,
                      **{key: value for key, value in kwargs.items() if key in parameters})
    monkeypatch.setattr(t, "assert_lease", bound)
    return bound


@pytest.mark.parametrize("phase", ["D1", "D2", "D3", "pilot", "probe"])
def test_terminal_phase_anchor_presence_enforced_before_mkdir_or_launch(tmp_path, monkeypatch, phase):
    args = runner_args(tmp_path, phase)
    mock_authorization(monkeypatch)
    if phase.startswith("D"):
        parent = tmp_path / "parent.pt"; parent.write_bytes(b"synthetic-unread-parent")
        args.parent_checkpoint = parent
    anchor = {"phase": "pilot", "supervisor_exit_code": 0} if phase in {"pilot", "probe"} else None
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"active_long_campaign": lease_for(args, phase, anchor)}))
    bind_state(monkeypatch, state)
    launches = []
    def launch(*args, **kwargs):
        launches.append(True)
        raise RuntimeError("Invalid lease reached worker launch")
    monkeypatch.setattr(t.subprocess, "Popen", launch)
    rejected = None
    try:
        t.run_supervised(args)
    except ValueError as error:
        rejected = error
    assert rejected is not None, "Invalid phase anchor reached supervisor launch boundary"
    assert "terminal receipt" in str(rejected)
    assert not launches and not args.run_dir.exists()


def test_terminal_guard_rejects_anchor_swap_even_between_resource_samples(tmp_path, monkeypatch):
    args = runner_args(tmp_path, "D1")
    anchor = {"phase": "pilot", "run_result_sha256": "a" * 64}
    lease = lease_for(args, "D1", anchor)
    path = tmp_path / "state.json"; path.write_text(json.dumps({"active_long_campaign": lease}))
    monkeypatch.setattr(s.time, "monotonic", lambda: 0.)
    monkeypatch.setattr(s, "utc_now", lambda: datetime(2026, 10, 24, 10, tzinfo=timezone.utc))
    monkeypatch.setattr(s, "current_rss_bytes", lambda pid: 100)
    monkeypatch.setattr(s, "peak_rss_bytes", lambda: 100)
    guard = s.Guard(deadline=100., run_id=args.run_id, identity_sha256=lease["identity_sha256"],
                    config_sha256=lease["config_sha256"], stream=io.StringIO(), state_path=path)
    guard.check(force=True)
    lease["parent_terminal_receipt"]["run_result_sha256"] = "b" * 64
    path.write_text(json.dumps({"active_long_campaign": lease}))
    with pytest.raises(s.GuardStop, match="terminal receipt changed"):
        guard.check()


def test_terminal_worker_constructor_rejects_actual_lease_anchor_before_model_or_env(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir()
    parent, _, target, anchor = _source(source)
    args = runner_args(tmp_path, "D1")
    args.config.write_text(json.dumps(target["config"]))
    args.identity.write_text(json.dumps(target))
    args.parent_checkpoint = parent
    args.identity_sha256 = i.file_hash(args.identity); args.config_sha256 = i.file_hash(args.config)
    args.run_dir.mkdir()
    anchor["run_result_sha256"] = "0" * 64
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"active_long_campaign": lease_for(args, "D1", anchor)}))
    bind_state(monkeypatch, path)
    models = []; environments = []
    def model():
        models.append(True)
        return torch.nn.Linear(2, 1)
    monkeypatch.setattr(t, "OmniscientEntityTeacher", model)
    monkeypatch.setattr(t.Experiment, "make_environment", lambda *a: environments.append(True))
    rejected = None; experiment = None
    try:
        experiment = t.Experiment(args, target["config"], target, NoopGuard())
    except ValueError as error:
        rejected = error
    finally:
        if experiment is not None:
            experiment.close()
    assert rejected is not None, "Worker bypass restored unanchored parent"
    assert not models and not environments


def completed_process(args):
    class Process:
        pid = 740120
        def __init__(self, *a, **kw):
            (args.run_dir / "worker-result.json").write_text(json.dumps({
                "status": "passed", "identity_sha256": i.file_hash(args.identity),
                "config_sha256": i.file_hash(args.config)}))
        def poll(self): return 0
        def wait(self, timeout): return 0
    return Process


@pytest.mark.parametrize("boundary", ["run-result.json", "artifact-sha256.json", "resources-close"])
def test_terminal_supervisor_recorded_signal_after_pass_publication_forces_nonzero(tmp_path, monkeypatch, boundary):
    args = runner_args(tmp_path)
    mock_authorization(monkeypatch)
    monkeypatch.setattr(t.subprocess, "Popen", completed_process(args))
    actual = t.save_json
    def publish(path, value):
        actual(path, value)
        if path.name == boundary:
            os.kill(os.getpid(), signal.SIGTERM)
    monkeypatch.setattr(t, "save_json", publish)
    if boundary == "resources-close":
        # Context exit is after both final artifacts were published, before return.
        original = s.cancellation_signals
        from contextlib import contextmanager
        @contextmanager
        def context():
            with original() as cancellation:
                yield cancellation
                os.kill(os.getpid(), signal.SIGTERM)
        monkeypatch.setattr(t, "cancellation_signals", context)
    status = t.run_supervised(args)
    assert status != 0, "Recorded late SIGTERM returned success after publishing a passing receipt"
    assert json.loads((args.run_dir / "run-result.json").read_text())["status"] == "passed"
    assert (args.run_dir / "artifact-sha256.json").exists()


@pytest.mark.parametrize("boundary", ["publication", "close"])
def test_terminal_worker_recorded_signal_cannot_silently_return_pass(tmp_path, monkeypatch, boundary):
    args = runner_args(tmp_path)
    args.run_dir.mkdir()
    started = t.time.monotonic()
    args.phase = "pilot"; args.config_sha256 = i.file_hash(args.config)
    args.identity_sha256 = i.file_hash(args.identity)
    args.consumed_wall_seconds = 0; args.execution_started_monotonic = started
    args.deadline_monotonic = started + 300
    mock_authorization(monkeypatch)
    class Experiment:
        progress = {}
        def __init__(self, *args): pass
        def pilot(self): return {"status": "passed", "phase": "pilot", "B_opened": False}
        def close(self):
            if boundary == "close": os.kill(os.getpid(), signal.SIGTERM)
        def checkpoint(self, tag): raise RuntimeError("No real learner in synthetic worker")
    monkeypatch.setattr(t, "Experiment", Experiment)
    actual = t.save_json
    def publish(path, value):
        actual(path, value)
        if boundary == "publication" and value["status"] == "passed":
            # Emulate first signal in deferred finalization, rather than a throw.
            signal.getsignal(signal.SIGTERM).__self__.defer()
            os.kill(os.getpid(), signal.SIGTERM)
    monkeypatch.setattr(t, "save_json", publish)
    status = t.worker(args)
    assert status != 0, "Recorded late worker SIGTERM silently returned success"
    assert json.loads((args.run_dir / "worker-result.json").read_text())["status"] == "passed"


def test_terminal_actual_evaluate_final_guard_expiry_never_authorizes_candidate(tmp_path, monkeypatch):
    from test_checkpoints import checkpoint, eval_result, simple_identity
    path = tmp_path / "candidate.pt"; _, digest = checkpoint(path)
    experiment = t.Experiment.__new__(t.Experiment)
    experiment.directory = tmp_path; experiment.config = i.default_config("pilot")
    experiment.model = torch.nn.Linear(2, 1); experiment.device = torch.device("cpu")
    experiment.actor_gradient_seen = experiment.critic_gradient_seen = True
    experiment.counters = {"phase_updates": 1}; experiment.last_metrics = None
    checks = []
    def expired(**kwargs):
        checks.append(True)
        if len(checks) == 3:
            raise s.GuardStop("Experiment wall guard expired after certificate")
    experiment.guard = SimpleNamespace(check=expired)
    monkeypatch.setattr(t, "evaluate", lambda *a, **kw: eval_result(2, 700))
    with pytest.raises(s.GuardStop, match="after certificate"):
        experiment.evaluate_checkpoint(path, digest, pilot_before=eval_result(.5, 500))
    assert json.loads(c.evaluation_path(path).read_text())["passed"] is True
    target = simple_identity(i.default_config("D1", parent_sha256=digest))
    anchor = {"run_id": "expired", "phase": "pilot", "run_result_sha256": "0" * 64,
              "checkpoint_sha256": digest, "evaluation_sha256": i.file_hash(c.evaluation_path(path)),
              "identity_sha256": "a" * 64, "config_sha256": "b" * 64, "supervisor_exit_code": 1}
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_valid_worker_restore_records_lease_anchor_and_preserves_rng(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir()
    parent, state, target, anchor = _source(source)
    args = runner_args(tmp_path, "D1")
    args.config.write_text(json.dumps(target["config"])); args.identity.write_text(json.dumps(target))
    args.identity_sha256 = i.file_hash(args.identity); args.config_sha256 = i.file_hash(args.config)
    args.parent_checkpoint = parent; args.run_dir.mkdir()
    ledger = tmp_path / "state.json"
    ledger.write_text(json.dumps({"active_long_campaign": lease_for(args, "D1", anchor)}))
    original_ledger = ledger.read_bytes(); bind_state(monkeypatch, ledger)
    monkeypatch.setattr(t, "OmniscientEntityTeacher", lambda: torch.nn.Linear(2, 1))
    initial_indices = []
    monkeypatch.setattr(t.Experiment, "make_environment", lambda self, indices: initial_indices.append(indices))
    experiment = t.Experiment(args, target["config"], target, NoopGuard())
    try:
        assert all(torch.equal(value, experiment.model.state_dict()[key]) for key, value in state["model"].items())
        assert torch.equal(torch.get_rng_state(), state["rng"]["torch_cpu"])
        lineage = json.loads((args.run_dir / "parent-lineage.json").read_text())
        assert lineage["parent_terminal_receipt"] == anchor
        assert initial_indices == [[0] * 64]
        assert ledger.read_bytes() == original_ledger
    finally:
        experiment.close()
