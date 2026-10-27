"""Inert ranking bundle adapter. No evaluator, checkpoint, or runtime imports."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

UPDATES = (180, 204, 276, 300, 324, 348)
SEEDS = tuple(range(0xD1000000, 0xD1000400))
CAP = 18000
SCHEMA = "expanded_D2_ranking_selection_v1"
RECORD_SCHEMA = "expanded_D2_selection_record_v2"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_pinned(path, pin, label):
    data = Path(path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if not isinstance(pin, str) or actual != pin:
        raise ValueError(label + " sha256 mismatch")
    return json.loads(data)


def _finite_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + " must be finite number")
    return value


def _candidate_pins(registration):
    candidates = registration.get("candidates")
    if not isinstance(candidates, dict) or set(candidates) != {str(x) for x in UPDATES}:
        raise ValueError("registration candidate set mismatch")
    pins = {}
    for update in UPDATES:
        candidate = candidates[str(update)]
        pin = candidate.get("checkpoint_sha256")
        if not isinstance(pin, str) or len(pin) != 64:
            raise ValueError("candidate checkpoint pin invalid")
        pins[update] = pin
    return pins


def _check_row(row, index, update):
    if not isinstance(row, dict) or row.get("seed") != SEEDS[index]:
        raise ValueError("rows must follow exact manifest seed order")
    if row.get("episode_index") != index:
        raise ValueError("episode index mismatch")
    alive = row.get("alive_frames")
    if type(alive) is not int or not 0 <= alive <= CAP:
        raise ValueError("alive_frames outside cap")
    if row.get("gameplay_frames") != alive + 1:
        raise ValueError("gameplay_frames accounting mismatch")
    terminated, truncated = row.get("terminated"), row.get("truncated")
    if type(terminated) is not bool or type(truncated) is not bool or terminated == truncated:
        raise ValueError("row termination flags invalid")
    if truncated and (alive != CAP or row.get("death_cause") is not None):
        raise ValueError("cap row telemetry invalid")
    if terminated and (alive >= CAP or not isinstance(row.get("death_cause"), str)):
        raise ValueError("death row telemetry invalid")
    for key in ("score", "objective_return"):
        _finite_number(row.get(key), key)
    if type(row.get("score_raw_fixed")) is not int or row["score"] != row["score_raw_fixed"] / 65536:
        raise ValueError("score fixed point mismatch")
    expected = row["score"] + alive / 100 - 5 * terminated
    if not math.isclose(row["objective_return"], expected, rel_tol=0, abs_tol=1e-9):
        raise ValueError("objective return mismatch")
    return alive


def _performance(values):
    ordered = sorted(values)
    q = len(ordered) // 4
    return {"worst": ordered[0], "q1_bottom_quarter_mean": sum(ordered[:q]) / q,
            "mean": sum(ordered) / len(ordered), "q4_top_quarter_mean": sum(ordered[-q:]) / q,
            "best": ordered[-1]}


def _same_performance(reported, computed):
    if not isinstance(reported, dict):
        raise ValueError("performance summary missing")
    for key, value in computed.items():
        actual = _finite_number(reported.get(key), "performance." + key)
        if not math.isclose(actual, value, rel_tol=0, abs_tol=1e-9):
            raise ValueError("reported performance mismatch: " + key)


def _identity(result, update, pins, registration_sha, evaluator_sha, runtime_sha,
              cohort_sha, manifest_sha):
    expected = {"complete": True, "candidate_update": update, "cohort_name": "ranking",
                "cohort_sha256": cohort_sha, "checkpoint_sha256": pins[update],
                "registration_sha256": registration_sha, "evaluator_sha256": evaluator_sha,
                "runtime_sha256": runtime_sha, "manifest_sha256": manifest_sha}
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError("ranking result identity mismatch: " + key)
    if result.get("episodes") != 1024:
        raise ValueError("ranking result must have 1024 episodes")


def produce_selection(bundle_path, bundle_sha256, registration_path, registration_sha256,
                      outer_receipt_path, outer_receipt_sha256, result_paths,
                      evaluator_sha256, runtime_sha256, cohort_sha256, manifest_sha256,
                      output_path):
    """Validate externally pinned artifacts and write an exclusive selection record."""
    bundle = read_pinned(bundle_path, bundle_sha256, "ranking bundle")
    registration = read_pinned(registration_path, registration_sha256, "registration")
    outer = read_pinned(outer_receipt_path, outer_receipt_sha256, "outer receipt")
    if bundle.get("schema") != SCHEMA or bundle.get("selection_only") is not True:
        raise ValueError("ranking bundle schema/status mismatch")
    if outer.get("raw_exit_code") != 0 or outer.get("stop_reason") is not None or outer.get("process_group_absent") is not True:
        raise ValueError("outer receipt not successful")
    if outer.get("registration_sha256") != registration_sha256:
        raise ValueError("outer receipt registration mismatch")
    if outer.get("evaluator_sha256") != evaluator_sha256 or outer.get("runtime_sha256") != runtime_sha256:
        raise ValueError("outer receipt evaluator/runtime mismatch")
    if registration.get("evaluator_sha256") not in (None, evaluator_sha256):
        raise ValueError("registration evaluator mismatch")
    if registration.get("runtime_sha256") not in (None, runtime_sha256):
        raise ValueError("registration runtime mismatch")
    pins = _candidate_pins(registration)
    if not isinstance(result_paths, dict) or set(result_paths) != set(UPDATES):
        raise ValueError("exact six candidate result paths required")
    candidates = bundle.get("candidate_results")
    if not isinstance(candidates, list) or len(candidates) != 6:
        raise ValueError("bundle must contain six candidate summaries")
    by_update = {}
    for summary in candidates:
        update = summary.get("candidate_update")
        if type(update) is not int or update in by_update:
            raise ValueError("duplicate or invalid candidate summary")
        by_update[update] = summary
    if set(by_update) != set(UPDATES):
        raise ValueError("bundle candidate set mismatch")

    refs, means = [], {}
    for update in UPDATES:
        path, result_pin = result_paths[update]
        result = read_pinned(path, result_pin, "ranking result")
        _identity(result, update, pins, registration_sha256, evaluator_sha256,
                  runtime_sha256, cohort_sha256, manifest_sha256)
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1024:
            raise ValueError("candidate rows must contain exactly 1024 entries")
        vals = [_check_row(row, i, update) for i, row in enumerate(rows)]
        perf = _performance(vals)
        _same_performance(result.get("performance"), perf)
        _same_performance(by_update[update].get("performance"), perf)
        if by_update[update].get("checkpoint_sha256") != pins[update]:
            raise ValueError("bundle checkpoint mismatch")
        means[update] = perf["mean"]
        refs.append({"path": str(Path(path).resolve()), "sha256": result_pin})
    winner = min(UPDATES, key=lambda update: (-means[update], update))
    if bundle.get("winner_update") != winner:
        raise ValueError("bundle winner differs from recomputed argmax")
    record = {"schema": RECORD_SCHEMA, "winner_update": winner,
              "winner_checkpoint_sha256": pins[winner],
              "incumbent_checkpoint_sha256": pins[348], "ranking_results": refs,
              "ranking_run_id": registration.get("run_id"),
              "registration_sha256": registration_sha256,
              "evaluator_sha256": evaluator_sha256, "runtime_sha256": runtime_sha256,
              "cohort_sha256": cohort_sha256, "manifest_sha256": manifest_sha256,
              "ranking_metric": "mean_alive_frames_all_1024_including_caps",
              "ranking_mean_alive_frames": means[winner],
              "confirmation_status": "no_confirmation" if winner == 348 else "eligible_for_parent_confirmation_gate",
              "evidence_limit": "selection preparation only; does not authorize confirmation or alter accepted incumbent"}
    if winner == 348:
        record["invocable_confirmation_record"] = False
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as f:
        json.dump(record, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")
        f.flush()
    return record


def validate_selection_record(record_path, record_sha256, registration_path,
                              registration_sha256, pinned_results, expected_run_id,
                              expected_evaluator_sha256, expected_runtime_sha256,
                              expected_cohort_sha256, expected_manifest_sha256):
    """Future-worker validator. pinned_results maps update to (path, sha256)."""
    record = read_pinned(record_path, record_sha256, "selection record")
    registration = read_pinned(registration_path, registration_sha256, "registration")
    pins = _candidate_pins(registration)
    if record.get("schema") != RECORD_SCHEMA or registration.get("run_id") != expected_run_id:
        raise ValueError("selection schema or registration run mismatch")
    expected = {"ranking_run_id": expected_run_id, "registration_sha256": registration_sha256,
                "evaluator_sha256": expected_evaluator_sha256,
                "runtime_sha256": expected_runtime_sha256,
                "cohort_sha256": expected_cohort_sha256,
                "manifest_sha256": expected_manifest_sha256}
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError("selection provenance mismatch: " + key)
    if len(pinned_results) != 6:
        raise ValueError("six external result path/hash pins required")
    means = {}
    for update in UPDATES:
        path, pin = pinned_results[update]
        result = read_pinned(path, pin, "ranking result")
        _identity(result, update, pins, registration_sha256, expected_evaluator_sha256,
                  expected_runtime_sha256, expected_cohort_sha256, expected_manifest_sha256)
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1024:
            raise ValueError("candidate rows must contain exactly 1024 entries")
        perf = _performance([_check_row(row, i, update) for i, row in enumerate(rows)])
        _same_performance(result.get("performance"), perf)
        means[update] = perf["mean"]
    winner = min(UPDATES, key=lambda update: (-means[update], update))
    if record.get("winner_update") != winner:
        raise ValueError("selection winner is not recomputed argmax")
    if record.get("winner_checkpoint_sha256") != pins[winner] or record.get("incumbent_checkpoint_sha256") != pins[348]:
        raise ValueError("selection checkpoint pin mismatch")
    if record.get("ranking_mean_alive_frames") != means[winner]:
        raise ValueError("selection winner metric mismatch")
    refs = record.get("ranking_results")
    expected_refs = [{"path": str(Path(pinned_results[u][0]).resolve()), "sha256": pinned_results[u][1]} for u in UPDATES]
    if refs != expected_refs:
        raise ValueError("selection result refs differ from external pins")
    if winner == 348 and (record.get("confirmation_status") != "no_confirmation" or record.get("invocable_confirmation_record") is not False):
        raise ValueError("348 winner must leave confirmation unopened")
    if winner != 348 and record.get("confirmation_status") != "eligible_for_parent_confirmation_gate":
        raise ValueError("confirmation eligibility marker invalid")
    return record
