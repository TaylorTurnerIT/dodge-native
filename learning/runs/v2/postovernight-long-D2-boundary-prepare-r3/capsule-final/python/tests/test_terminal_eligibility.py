"""Terminal-source authority controls; all fixtures are synthetic CPU artifacts."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest
import torch

from dodge_rl import checkpoints as c
from dodge_rl.identity import default_config, file_hash


def _write(path: Path, value) -> None:
    # Nonfinite fixture values are intentional rejection controls.
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def refresh_manifest(directory: Path) -> dict:
    entries = {path.name: file_hash(path) for path in sorted(directory.iterdir())
               if path.is_file() and path.name != "artifact-sha256.json"}
    _write(directory / "artifact-sha256.json", entries)
    return entries


def terminal_receipt(path: Path, state=None, digest=None) -> dict:
    """Add a complete terminal fixture around an existing checkpoint and certificate.

    Lease hashes describe the source documents. Run copies use different JSON
    formatting, as the actual runner does, and must be compared semantically.
    """
    directory = path.parent
    state = c.load_checkpoint(path) if state is None else state
    digest = file_hash(path) if digest is None else digest
    identity = state["identity"]
    config = identity["config"]
    _write(directory / "identity.json", identity)
    _write(directory / "registered-config.json", config)
    source_hash = lambda value: hashlib.sha256(json.dumps(value, indent=4).encode()).hexdigest()
    identity_digest, config_digest = source_hash(identity), source_hash(config)
    proof = json.loads(c.evaluation_path(path).read_text())
    worker = {"status": "passed", "phase": config["phase"],
              "identity_sha256": identity_digest, "config_sha256": config_digest,
              "checkpoint": path.name, "checkpoint_sha256": digest,
              "evaluation": proof, "B_opened": False, "elapsed_seconds": 1.0}
    result = {"status": "passed", "run_id": "source-run", "phase": config["phase"],
              "identity_sha256": identity_digest, "config_sha256": config_digest,
              "worker_exit_code": 0, "automatic_retries": 0, "limits_relaxed": False,
              "B_opened": False, "consumed_phase_wall_seconds": 1.0,
              "prior_consumed_wall_seconds": 0.0, "elapsed_seconds": 1.0,
              "finished_at_utc": "2026-10-24T10:00:01+00:00", "worker_result": worker}
    _write(directory / "worker-result.json", worker)
    _write(directory / "run-result.json", result)
    refresh_manifest(directory)
    return {"run_id": result["run_id"], "phase": config["phase"],
            "run_result_sha256": file_hash(directory / "run-result.json"),
            "checkpoint_sha256": digest, "evaluation_sha256": file_hash(c.evaluation_path(path)),
            "identity_sha256": identity_digest, "config_sha256": config_digest,
            "supervisor_exit_code": 0}


def transition(path: Path, target: dict, anchor: dict):
    """Exercise old behavior directly when running the frozen r2 control.

    This adapter permits a behavioral comparison. Missing new API keywords are
    never accepted as evidence that the old implementation was defective.
    """
    if "terminal_anchor" in inspect.signature(c.validate_transition).parameters:
        return c.validate_transition(path, target, terminal_anchor=anchor)
    return c.validate_transition(path, target)


def _source(directory: Path, *, tag="candidate"):
    from test_checkpoints import certificate, checkpoint, simple_identity
    path = directory / "candidate.pt"
    state, digest = checkpoint(path, tag=tag)
    certificate(path, digest)
    anchor = terminal_receipt(path, state, digest)
    target = simple_identity(default_config("D1", parent_sha256=digest))
    return path, state, target, anchor


def _rewrite_result(path: Path, anchor: dict, mutate):
    result_path = path.parent / "run-result.json"
    result = json.loads(result_path.read_text())
    mutate(result)
    _write(result_path, result)
    anchor["run_result_sha256"] = file_hash(result_path)
    refresh_manifest(path.parent)


def test_terminal_exact_candidate_preserves_weights_rng_and_parent_bytes(tmp_path):
    path, state, target, anchor = _source(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    rng_before = torch.get_rng_state().clone()
    loaded, proof = transition(path, target, anchor)
    assert proof["passed"] is True
    assert anchor["identity_sha256"] != file_hash(tmp_path / "identity.json")
    assert anchor["config_sha256"] != file_hash(tmp_path / "registered-config.json")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before
    assert torch.equal(torch.get_rng_state(), rng_before)
    assert torch.equal(loaded["rng"]["torch_cpu"], state["rng"]["torch_cpu"])
    for key, value in state["model"].items():
        assert torch.equal(loaded["model"][key], value)


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_terminal_nonpassing_supervisor_rejects_passing_candidate(tmp_path, status):
    path, _, target, anchor = _source(tmp_path)
    _rewrite_result(path, anchor, lambda result: result.update(status=status))
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_missing_supervisor_receipt_rejects_passing_candidate(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    (tmp_path / "run-result.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        transition(path, target, anchor)


def test_terminal_worker_only_pass_cannot_override_failed_supervisor(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    _rewrite_result(path, anchor, lambda result: result.update(status="failed", worker_exit_code=1))
    assert json.loads((tmp_path / "worker-result.json").read_text())["status"] == "passed"
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("field,value", [
    ("worker_exit_code", 1), ("worker_exit_code", False),
    ("automatic_retries", 1), ("automatic_retries", False),
    ("limits_relaxed", True), ("B_opened", True),
    ("phase", "D1"), ("run_id", "another-run"),
    ("identity_sha256", "a" * 64), ("config_sha256", "b" * 64),
])
def test_terminal_supervisor_fields_reject_even_with_updated_index_and_pin(tmp_path, field, value):
    path, _, target, anchor = _source(tmp_path)
    _rewrite_result(path, anchor, lambda result: result.update({field: value}))
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("consumed", [300.001, -0.001, float("nan"), float("inf"), float("-inf"), True, "1"])
def test_terminal_invalid_or_late_consumed_phase_budget_rejects(tmp_path, consumed):
    path, _, target, anchor = _source(tmp_path)
    _rewrite_result(path, anchor, lambda result: result.update(consumed_phase_wall_seconds=consumed))
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("field", [
    "run_id", "phase", "run_result_sha256", "checkpoint_sha256", "evaluation_sha256",
    "identity_sha256", "config_sha256", "supervisor_exit_code",
])
def test_terminal_parent_anchor_each_field_is_authoritative(tmp_path, field):
    path, _, target, anchor = _source(tmp_path)
    anchor[field] = 1 if field == "supervisor_exit_code" else ("D1" if field == "phase" else "0" * 64)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_parent_observed_exit_requires_exact_integer_zero(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    anchor["supervisor_exit_code"] = False
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("field,value", [
    ("status", "failed"), ("phase", "D1"), ("identity_sha256", "a" * 64),
    ("config_sha256", "b" * 64), ("checkpoint", "../candidate.pt"),
    ("checkpoint_sha256", "c" * 64), ("B_opened", True),
])
def test_terminal_worker_claims_must_match_source_and_exact_artifacts(tmp_path, field, value):
    path, _, target, anchor = _source(tmp_path)
    def mutate(result):
        result["worker_result"][field] = value
        _write(tmp_path / "worker-result.json", result["worker_result"])
    _rewrite_result(path, anchor, mutate)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_worker_file_must_equal_supervisor_copy(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    worker = json.loads((tmp_path / "worker-result.json").read_text())
    worker["elapsed_seconds"] += 0.1
    _write(tmp_path / "worker-result.json", worker)
    refresh_manifest(tmp_path)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("tag", ["candidate", "periodic", "failure", "timeout", "interrupted_mid_update"])
def test_terminal_other_checkpoint_in_same_run_is_not_the_run_end_candidate(tmp_path, tag):
    from test_checkpoints import certificate, checkpoint, simple_identity
    _, _, _, anchor = _source(tmp_path)
    other = tmp_path / "other.pt"
    _, digest = checkpoint(other, tag=tag)
    certificate(other, digest)
    refresh_manifest(tmp_path)
    target = simple_identity(default_config("D1", parent_sha256=digest))
    with pytest.raises(ValueError):
        transition(other, target, anchor)


@pytest.mark.parametrize("tag", ["periodic", "pilot_initial", "diagnostic", "failure", "timeout", "probe_diagnostic"])
def test_terminal_even_exact_run_end_requires_candidate_allowlist(tmp_path, tag):
    path, _, target, anchor = _source(tmp_path, tag=tag)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_edited_certificate_rejects_with_unchanged_parent_anchor(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    c.evaluation_path(path).write_text(c.evaluation_path(path).read_text() + "\n")
    refresh_manifest(tmp_path)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_evaluation_file_must_equal_worker_evaluation(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    proof = json.loads(c.evaluation_path(path).read_text())
    proof["completed_training_updates"] += 1
    _write(c.evaluation_path(path), proof)
    anchor["evaluation_sha256"] = file_hash(c.evaluation_path(path))
    refresh_manifest(tmp_path)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("artifact", ["run-result.json", "worker-result.json", "candidate.pt", "candidate.pt.evaluation.json",
                                      "identity.json", "registered-config.json"])
def test_terminal_manifest_critical_entries_cannot_be_inconsistent(tmp_path, artifact):
    path, _, target, anchor = _source(tmp_path)
    manifest = json.loads((tmp_path / "artifact-sha256.json").read_text())
    manifest[artifact] = "0" * 64
    _write(tmp_path / "artifact-sha256.json", manifest)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_missing_manifest_cannot_authorize_parent(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    (tmp_path / "artifact-sha256.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        transition(path, target, anchor)


@pytest.mark.parametrize("artifact", ["identity.json", "registered-config.json"])
def test_terminal_copied_identity_config_must_semantically_match_checkpoint(tmp_path, artifact):
    path, _, target, anchor = _source(tmp_path)
    copied = json.loads((tmp_path / artifact).read_text())
    if artifact == "identity.json":
        copied["sources"]["source.py"] = "different-source"
    else:
        copied["ppo"]["gamma"] = 0.9
    _write(tmp_path / artifact, copied)
    refresh_manifest(tmp_path)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


def test_terminal_whitespace_replacement_of_pinned_run_result_rejects(tmp_path):
    path, _, target, anchor = _source(tmp_path)
    receipt = tmp_path / "run-result.json"
    receipt.write_text(receipt.read_text() + "\n")
    refresh_manifest(tmp_path)
    with pytest.raises(ValueError):
        transition(path, target, anchor)


@pytest.mark.parametrize("source_phase,target_phase", [("D1", "D2"), ("D2", "D3")])
def test_terminal_valid_registered_stage_source_remains_eligible(tmp_path, source_phase, target_phase):
    from test_checkpoints import checkpoint, eval_result, simple_identity
    path = tmp_path / "candidate.pt"
    identity = simple_identity(default_config(source_phase, parent_sha256="a" * 64))
    state, digest = checkpoint(path, identity=identity)
    score, alive = (10, 1500) if source_phase == "D1" else (50, 3060)
    _write(c.evaluation_path(path), {"phase": source_phase, "checkpoint_sha256": digest,
           "complete": True, "passed": True,
           "evaluations": {source_phase: eval_result(score, alive, source_phase)}})
    anchor = terminal_receipt(path, state, digest)
    target = simple_identity(default_config(target_phase, parent_sha256=digest))
    loaded, proof = transition(path, target, anchor)
    assert proof["passed"] and loaded["identity"] == identity


@pytest.mark.parametrize("field", ["run_id", "phase", "run_result_sha256", "checkpoint_sha256", "evaluation_sha256",
                                    "identity_sha256", "config_sha256", "supervisor_exit_code"])
def test_terminal_manifest_consistency_does_not_replace_missing_parent_authority(tmp_path, field):
    path, _, target, anchor = _source(tmp_path)
    del anchor[field]
    with pytest.raises(ValueError):
        transition(path, target, anchor)
