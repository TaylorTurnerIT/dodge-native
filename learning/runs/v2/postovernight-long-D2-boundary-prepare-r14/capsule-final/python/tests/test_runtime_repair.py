"""Behavioral regressions for frozen M3 runtime findings; no native campaigns."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
import torch

from dodge_rl import checkpoints as c
from dodge_rl import identity as i
from dodge_rl import train_teacher as t


class NoopGuard:
    maximum_rss = maximum_mps = 0

    def __init__(self, **kwargs):
        self.deadline = kwargs.get("deadline", 1800)

    def check(self, **kwargs):
        pass


def runner_args(tmp_path, phase="pilot"):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(i.default_config(phase, parent_sha256="a" * 64
                                                if phase.startswith("D") else None)))
    identity = tmp_path / "identity.json"
    identity.write_text("{}")
    return SimpleNamespace(config=config, identity=identity, run_dir=tmp_path / "run",
                           command=phase if phase == "pilot" else "stage", stage=phase,
                           run_id="synthetic-repair", resume_checkpoint=None,
                           parent_checkpoint=None)


def mock_authorization(monkeypatch):
    monkeypatch.setattr(t, "Guard", NoopGuard)
    monkeypatch.setattr(t, "verify_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(t, "assert_lease", lambda *args, **kwargs: {})
    monkeypatch.setattr(t, "utc_now", lambda: datetime(2026, 10, 24, 10, tzinfo=timezone.utc))


@pytest.mark.parametrize("error", [KeyboardInterrupt("cancelled"), SystemExit(17), BaseException("abort")])
def test_supervisor_baseexception_keeps_receipt_and_reaps_owned_worker(tmp_path, monkeypatch, error):
    args = runner_args(tmp_path)
    mock_authorization(monkeypatch)
    checks = []

    class InterruptGuard(NoopGuard):
        def check(self, **kwargs):
            checks.append(True)
            if len(checks) == 2:
                raise error

    class Process:
        pid = 740101

        def poll(self):
            return None

    owned = Process()
    stopped = []
    monkeypatch.setattr(t, "Guard", InterruptGuard)
    monkeypatch.setattr(t.subprocess, "Popen", lambda *a, **kw: owned)
    monkeypatch.setattr(t, "stop_owned", lambda process: stopped.append(process) or {"reaped": True})
    escaped = None
    try:
        status = t.run_supervised(args)
    except BaseException as caught:
        escaped = caught
        status = None
    assert escaped is None, f"Cancellation escaped before owned-worker cleanup: {escaped!r}"
    assert status == 1 and stopped == [owned]
    receipt = json.loads((args.run_dir / "run-result.json").read_text())
    assert receipt["status"] == "failed" and receipt["owned_process_stop"]["reaped"]
    assert receipt["automatic_retries"] == 0 and not receipt["limits_relaxed"]
    assert (args.run_dir / "artifact-sha256.json").exists()


def child_bootstrap():
    """Children execute the same explicitly selected source as the pytest process."""
    source_root = Path(t.__file__).resolve().parents[2]
    return f"""
import importlib.util, pathlib, sys, hashlib
import dodge_rl
source_root = pathlib.Path({str(source_root)!r})
for name in ('supervision', 'checkpoints', 'train_teacher'):
    path = source_root / 'python/dodge_rl' / (name + '.py')
    spec = importlib.util.spec_from_file_location('dodge_rl.' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    setattr(dodge_rl, name, module)
    spec.loader.exec_module(module)
    print('EXECUTED_SOURCE', name, str(path), hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)
"""


def wait_file(path, process, seconds=10):
    deadline = time.monotonic() + seconds
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(.02)
    assert path.exists(), f"Synthetic child did not become ready; returncode={process.poll()}"


def test_supervisor_real_sigterm_checkpoints_worker_and_keeps_terminal_receipt(tmp_path):
    script = child_bootstrap() + f"""
import json, os, signal, subprocess, time
from datetime import datetime, timezone
from types import SimpleNamespace
from dodge_rl import train_teacher as t, identity as i
directory = pathlib.Path({str(tmp_path)!r})
config = directory / 'config.json'; config.write_text(json.dumps(i.default_config('pilot')))
identity = directory / 'identity.json'; identity.write_text('{{}}')
args = SimpleNamespace(config=config, identity=identity, run_dir=directory/'run',
    command='pilot',run_id='synthetic-sigterm',resume_checkpoint=None,parent_checkpoint=None)
class Guard:
    maximum_rss = maximum_mps = 0
    def __init__(self, **kwargs): pass
    def check(self, **kwargs): pass
t.Guard=Guard; t.assert_lease=lambda *a, **kw: {{}}; t.verify_inputs=lambda *a, **kw: {{}}
t.utc_now=lambda:datetime(2026,10,24,10,tzinfo=timezone.utc)
t.current_rss_bytes=lambda pid:100
real_popen=subprocess.Popen
worker_code = '''import os,signal,time,pathlib,sys
directory=pathlib.Path({str(tmp_path)!r})
def stop(*args):
    (directory/'cooperative-diagnostic.pt').write_bytes(b'synthetic checkpoint opportunity')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
(directory/'worker-ready').write_text(str(os.getpid()))
time.sleep(60)
'''
t.subprocess.Popen=lambda command, **kwargs:real_popen([sys.executable,'-B','-c',worker_code],**kwargs)
raise SystemExit(t.run_supervised(args))
"""
    script_path = tmp_path / "supervisor.py"
    script_path.write_text(script)
    process = subprocess.Popen([sys.executable, "-B", str(script_path)], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    worker_pid = None
    try:
        wait_file(tmp_path / "worker-ready", process)
        worker_pid = int((tmp_path / "worker-ready").read_text())
        os.kill(process.pid, signal.SIGTERM)
        output, _ = process.communicate(timeout=15)
        (tmp_path / "supervisor-output.log").write_text(output)
        assert process.returncode == 1, output
        receipt = json.loads((tmp_path / "run/run-result.json").read_text())
        assert receipt["status"] == "failed" and receipt["owned_process_stop"]["reaped"]
        assert receipt["owned_process_stop"]["owned_pid"] == worker_pid
        assert (tmp_path / "cooperative-diagnostic.pt").exists()
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        # Frozen-source controls intentionally expose an orphan. Clean only the
        # test-owned group, retaining a record of this harness cleanup.
        if worker_pid is not None:
            try:
                os.killpg(worker_pid, signal.SIGTERM)
                (tmp_path / "harness-cleanup.json").write_text(json.dumps({"owned_pgid": worker_pid,
                    "reason": "negative-control orphan or surviving test-owned descendant"}))
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("interrupt", ["SIGTERM", "KeyboardInterrupt"])
def test_worker_cancellation_attempts_tagged_diagnostic_checkpoint(tmp_path, interrupt):
    action = "os.kill(os.getpid(), signal.SIGTERM)" if interrupt == "SIGTERM" else "raise KeyboardInterrupt('cancelled')"
    script = child_bootstrap() + f"""
import json, os, signal, time
from datetime import datetime, timezone
from types import SimpleNamespace
from dodge_rl import train_teacher as t, identity as i, checkpoints as c
directory=pathlib.Path({str(tmp_path)!r})
config=directory/'config.json';config.write_text(json.dumps(i.default_config('pilot')))
class Guard:
    maximum_rss=maximum_mps=0
    def __init__(self, **kwargs): pass
    def check(self, **kwargs): pass
class Experiment:
    progress={{'in_update':True,'complete':False,'optimizer_steps':1}}
    def __init__(self,*args): pass
    def pilot(self):
        {action}
    def checkpoint(self,tag):
        path=directory/(tag+'.pt')
        return path,c.save_checkpoint(path,{{'tag':tag,'update_progress':self.progress}})
    def close(self): (directory/'closed').write_text('yes')
t.Guard=Guard;t.Experiment=Experiment;t.verify_inputs=lambda *a:{{}};t.assert_lease=lambda *a, **kw:{{}}
t.utc_now=lambda:datetime(2026,10,24,10,tzinfo=timezone.utc)
started=time.monotonic()
args=SimpleNamespace(config=config,config_sha256=i.file_hash(config),identity_sha256='a'*64,
    phase='pilot',consumed_wall_seconds=0,execution_started_monotonic=started,
    deadline_monotonic=started+300,run_dir=directory,run_id='synthetic-worker',resume_checkpoint=None)
raise SystemExit(t.worker(args))
"""
    path = tmp_path / "worker.py"
    path.write_text(script)
    result = subprocess.run([sys.executable, "-B", str(path)], capture_output=True, text=True, timeout=15)
    (tmp_path / "worker-output.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 1, result.stdout + result.stderr
    receipt = json.loads((tmp_path / "worker-result.json").read_text())
    assert receipt["status"] == "failed" and receipt["checkpoint_tag"] == "interrupted_mid_update"
    assert receipt["update_progress"]["optimizer_steps"] == 1
    assert i.file_hash(tmp_path / receipt["checkpoint"]) == receipt["checkpoint_sha256"]
    assert (tmp_path / "closed").exists()


@pytest.mark.parametrize("tag,progress", [
    ("interrupted_mid_update", {"in_update": True, "complete": False, "optimizer_steps": 1}),
    ("periodic", {"in_update": False, "complete": False, "optimizer_steps": 1}),
])
def test_interrupted_resume_rejects_before_stage_entry_candidate(tmp_path, monkeypatch, tag, progress):
    from test_checkpoints import simple_identity
    config = i.default_config("D1", parent_sha256="a" * 64)
    identity = simple_identity(config)
    model = torch.nn.Linear(2, 1)
    optimizer = t.make_optimizer(model, config)
    state = c.make_state(model, optimizer, identity,
                         {"phase_updates": 0, "updates": 0, "optimizer_steps": 0, "checkpoint_index": 0},
                         tag=tag, progress=progress)
    state["run_context"] = {"consumed_wall_seconds": 100}
    path = tmp_path / "partial.pt"
    digest = c.save_checkpoint(path, state)
    original = path.read_bytes()
    args = SimpleNamespace(run_dir=tmp_path, resume_checkpoint=path,
                           resume_checkpoint_sha256=digest, parent_checkpoint=None,
                           consumed_wall_seconds=100)
    monkeypatch.setattr(t, "OmniscientEntityTeacher", lambda: torch.nn.Linear(2, 1))
    monkeypatch.setattr(t.Experiment, "make_environment", lambda self, indices: setattr(self, "env", object()))
    candidates = []
    monkeypatch.setattr(t.Experiment, "checkpoint", lambda self, tag:
                        candidates.append(tag) or (tmp_path / "candidate.pt", "digest"))
    monkeypatch.setattr(t.Experiment, "evaluate_checkpoint", lambda *a, **kw: {"passed": True})
    experiment = None
    rejected = None
    try:
        experiment = t.Experiment(args, config, identity, NoopGuard())
        experiment.stage()
    except ValueError as error:
        rejected = error
    finally:
        if experiment is not None:
            experiment.close()
    assert rejected is not None, f"Partially updated learner reached stage candidate: {candidates}"
    assert "Interrupted/incomplete" in str(rejected)
    assert candidates == [] and path.read_bytes() == original


def test_restore_partial_update_refuses_before_model_mutation(tmp_path):
    from test_checkpoints import simple_identity
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.Adam(model.parameters())
    state = c.make_state(model, optimizer, simple_identity(), {}, tag="interrupted_mid_update",
                         progress={"in_update": True, "complete": False, "optimizer_steps": 1})
    state["model"]["weight"].fill_(123)
    before = copy.deepcopy(model.state_dict())
    rejected = None
    try:
        c.restore_learner(state, model, optimizer)
    except ValueError as error:
        rejected = error
    assert rejected is not None, "Interrupted update restored into a live learner"
    assert all(torch.equal(value, model.state_dict()[name]) for name, value in before.items())


@pytest.mark.parametrize("consumed", [0, 1600, 1799.9])
def test_checkpoint_time_cannot_grant_same_phase_resume_allowance(consumed):
    config = i.default_config("D1", parent_sha256="a" * 64)
    state = {"run_context": {"consumed_wall_seconds": consumed}}
    with pytest.raises(ValueError, match="Same-phase resume disabled"):
        t.remaining_phase_budget(config, state)
    assert t.remaining_phase_budget(config, None) == (0, 1800)


@pytest.mark.parametrize("claimed_anchor", [None, "stale", "mismatching"])
def test_supervisor_rejects_same_phase_resume_before_launch(tmp_path, monkeypatch, claimed_anchor):
    from test_checkpoints import simple_identity
    args = runner_args(tmp_path, "D1")
    config = json.loads(args.config.read_text())
    model = torch.nn.Linear(2, 1)
    optimizer = t.make_optimizer(model, config)
    state = c.make_state(model, optimizer, simple_identity(config), {"phase_updates": 8},
                         tag="periodic", progress={"in_update": False, "complete": True})
    state["run_context"] = {"consumed_wall_seconds": 1600}
    args.resume_checkpoint = tmp_path / "checkpoint-at-1600.pt"
    c.save_checkpoint(args.resume_checkpoint, state)
    # Even CLI claims about terminal consumption cannot enable the disabled
    # path. The real prior attempt used its entire 1800-second allowance.
    terminal = tmp_path / "prior-run-result.json"
    terminal.write_text(json.dumps({"consumed_phase_wall_seconds": 1800, "status": "failed"}))
    args.prior_terminal_receipt = terminal if claimed_anchor is not None else None
    args.prior_terminal_receipt_sha256 = claimed_anchor
    mock_authorization(monkeypatch)
    launched = []

    class Process:
        pid = 740102

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    def launch(*a, **kw):
        launched.append(True)
        (args.run_dir / "worker-result.json").write_text(json.dumps({"status": "passed",
            "identity_sha256": i.file_hash(args.identity), "config_sha256": i.file_hash(args.config)}))
        return Process()

    monkeypatch.setattr(t.subprocess, "Popen", launch)
    rejected = None
    try:
        t.run_supervised(args)
    except ValueError as error:
        rejected = error
    assert rejected is not None, "Supervisor launched a worker using stale checkpoint consumption"
    assert "Same-phase resume disabled" in str(rejected)
    assert launched == [] and not args.run_dir.exists()


@pytest.mark.parametrize("resume_path", [False, True])
def test_internal_worker_rejects_unanchored_same_phase_resume_before_identity(tmp_path, monkeypatch, resume_path):
    args = runner_args(tmp_path, "D1")
    args.run_dir.mkdir()
    args.phase = "D1"
    args.config_sha256 = i.file_hash(args.config)
    args.identity_sha256 = i.file_hash(args.identity)
    args.resume_checkpoint = tmp_path / "periodic-at-1600.pt" if resume_path else None
    args.resume_checkpoint_sha256 = "d" * 64
    args.consumed_wall_seconds = 1600
    args.execution_started_monotonic = 0
    args.deadline_monotonic = 200
    mock_authorization(monkeypatch)
    monkeypatch.setattr(t.time, "monotonic", lambda: 1.)
    entered = []
    monkeypatch.setattr(t, "verify_inputs", lambda *a: entered.append("identity") or {})

    class FakeExperiment:
        progress = {}

        def __init__(self, *a):
            entered.append("experiment")

        def stage(self):
            entered.append("candidate")
            return {"status": "passed"}

        def close(self):
            pass

    monkeypatch.setattr(t, "Experiment", FakeExperiment)
    rejected = None
    try:
        t.worker(args)
    except ValueError as error:
        rejected = error
    assert rejected is not None, f"Internal worker granted extra checkpoint-local allowance: {entered}"
    assert "Same-phase resume disabled" in str(rejected) or "checkpoint-local" in str(rejected)
    assert entered == []


class ProbePolicy(torch.nn.Module):
    def __init__(self, failure):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.zeros(1))
        self.measured_device = "cpu"
        self.failure = failure

    def to(self, device):
        self.measured_device = str(device)
        return self

    def forward(self, *args):
        value = float("nan") if self.measured_device == "mps" and self.failure == "inference" else 0.
        return SimpleNamespace(logits=torch.full((1, 9), value), values=torch.zeros(1))


def probe_fixture(tmp_path, monkeypatch, failure, available=True):
    experiment = t.Experiment.__new__(t.Experiment)
    experiment.directory = tmp_path
    experiment.config = i.default_config("probe")
    experiment.config["rollout_steps"] = 1
    experiment.config["probe_devices"] = ["cpu", "mps"]
    experiment.model = ProbePolicy(failure)
    experiment.identity = {}
    experiment.counters = {}
    experiment.device = torch.device("cpu")
    experiment.env = object()
    experiment.ppo = t.PPOConfig()
    experiment.guard = NoopGuard()
    experiment.episodes = io.StringIO()
    experiment.make_environment = lambda: None
    initial = tmp_path / "initial.pt"
    initial_digest = c.save_checkpoint(initial, {"tag": "probe_diagnostic"})
    experiment.checkpoint = lambda tag: (initial, initial_digest)
    batch = SimpleNamespace(**{name: torch.zeros((1, 1, 1)) for name in t.OBSERVATION_KEYS},
                            raw_rewards=torch.zeros((1, 1)), score_delta_raw_fixed=torch.zeros((1, 1)),
                            alive_raw_frames=torch.zeros((1, 1)), elapsed_raw_frames=torch.zeros((1, 1)))
    collection = SimpleNamespace(batch=batch, completed_episodes=[], reset_info=[])
    monkeypatch.setattr(t, "collect_rollout", lambda *a, **kw: collection)
    monkeypatch.setattr(t, "synchronize", lambda *a: None)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: available)
    monkeypatch.setattr(c, "make_state", lambda *a, **kw: {"tag": "probe_diagnostic"})

    def update(candidate, *args, **kwargs):
        if candidate.measured_device == "mps" and failure != "inference":
            raise ValueError({"loss": "Nonfinite PPO loss", "audit": "Raw reward audit failed",
                              "unexpected": "Unexpected measured-device failure"}[failure])
        return {"optimizer_steps": 1, "epochs_completed": 1}

    monkeypatch.setattr(t, "ppo_update", update)
    return experiment


@pytest.mark.parametrize("failure", ["inference", "loss", "audit", "unexpected"])
def test_probe_device_correctness_failure_cannot_become_cpu_pass(tmp_path, monkeypatch, failure):
    experiment = probe_fixture(tmp_path, monkeypatch, failure)
    rejected = None
    result = None
    try:
        result = experiment.probe()
    except ValueError as error:
        rejected = error
    assert rejected is not None, f"Measured device failure was masked by selected CPU: {result}"
    failure_receipt = json.loads((tmp_path / "probe-mps-failure.json").read_text())
    assert failure_receipt["status"] == "failed" and not failure_receipt["automatic_retry"]
    assert failure_receipt["traceback"]
    assert (tmp_path / "probe-cpu-updated.pt").exists() and (tmp_path / "probe-rollout.pt").exists()


def test_unavailable_mps_comparison_remains_distinct_from_correctness_failure(tmp_path, monkeypatch):
    experiment = probe_fixture(tmp_path, monkeypatch, "inference", available=False)
    result = experiment.probe()
    assert result["status"] == "passed" and result["selected_device"] == "cpu"
    assert result["measurements"][1] == {"device": "mps", "status": "unavailable"}


def test_device_selector_rejects_failed_rows_even_with_completed_cpu():
    rows = [{"device": "cpu", "status": "completed", "optimizer_steps": 1,
             "metrics": {"epochs_completed": 1}, "measured_inference_plus_update_seconds": 1},
            {"device": "mps", "status": "failed", "error": "Nonfinite device probe"}]
    with pytest.raises(ValueError, match="correctness failure"):
        t.choose_probe_device(rows)
