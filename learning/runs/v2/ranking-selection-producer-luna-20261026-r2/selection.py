"""Inert adapter for pinned R5 ranking artifacts. Stdlib only."""
import hashlib
import json
import math
from pathlib import Path

UPDATES = (180, 204, 276, 300, 324, 348)
SEEDS = tuple(range(0xD1000000, 0xD1000400))
CAP = 18000
RANKING_SCHEMA = "expanded_D2_ranking_selection_v1"
DEATH_CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
                "static_pattern_rect", "moving_pattern_rect", "unknown", "unavailable")


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256(path):
    return digest_bytes(Path(path).read_bytes())


def read_pinned(path, pin, label):
    data = Path(path).read_bytes()
    if digest_bytes(data) != pin:
        raise ValueError(label + " sha256 mismatch")
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(label + " invalid JSON") from exc


def runtime_digest(registration):
    members = registration.get("runtime", {}).get("member_sha256")
    if not isinstance(members, dict) or len(members) != 13:
        raise ValueError("registration must pin exact 13-member runtime map")
    canonical = json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
    return digest_bytes(canonical)


def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + " must be finite")
    return value


def _pins(registration):
    candidates = registration.get("candidates")
    if not isinstance(candidates, dict) or set(candidates) != {str(u) for u in UPDATES}:
        raise ValueError("registration candidate set mismatch")
    out = {}
    for update in UPDATES:
        entry = candidates[str(update)]
        if entry.get("phase_update") != update:
            raise ValueError("candidate phase_update mismatch")
        pin = entry.get("checkpoint_sha256")
        if not isinstance(pin, str) or len(pin) != 64:
            raise ValueError("candidate checkpoint pin invalid")
        out[update] = pin
    return out


def _row_alive(row, i):
    if not isinstance(row, dict) or type(row.get("seed")) is not int or row["seed"] != SEEDS[i]:
        raise ValueError("rows must follow exact registered manifest seed order")
    if row.get("episode_index") != i:
        raise ValueError("episode index mismatch")
    alive = row.get("alive_frames")
    if type(alive) is not int or not 0 <= alive <= CAP or row.get("gameplay_frames") != alive + 1:
        raise ValueError("alive/gameplay frame accounting invalid")
    term, trunc = row.get("terminated"), row.get("truncated")
    if type(term) is not bool or type(trunc) is not bool or term == trunc:
        raise ValueError("termination flags invalid")
    if trunc and (alive != CAP or row.get("death_cause") is not None):
        raise ValueError("cap row fields invalid")
    if term and (alive >= CAP or row.get("death_cause") not in DEATH_CAUSES):
        raise ValueError("terminated row fields invalid")
    score = _finite(row.get("score"), "score")
    objective = _finite(row.get("objective_return"), "objective_return")
    if type(row.get("score_raw_fixed")) is not int or score != row["score_raw_fixed"] / 65536:
        raise ValueError("score fixed-point identity mismatch")
    expected = score + alive / 100 - 5 * term
    if not math.isclose(objective, expected, rel_tol=0, abs_tol=1e-9):
        raise ValueError("objective-return identity mismatch")
    return alive


def _metrics(values):
    ordered = sorted(values)
    q = len(ordered) // 4
    return {"worst": ordered[0], "q1_bottom_quarter_mean": sum(ordered[:q]) / q,
            "mean": sum(ordered) / len(ordered), "q4_top_quarter_mean": sum(ordered[-q:]) / q,
            "best": ordered[-1]}


def _check_metrics(reported, derived, label):
    if not isinstance(reported, dict):
        raise ValueError(label + " performance missing")
    for key, expected in derived.items():
        actual = _finite(reported.get(key), label + " performance." + key)
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9):
            raise ValueError(label + " performance mismatch: " + key)


def _validate_result(result, update, reg_sha, evaluator_sha, runtime_sha,
                     cohort_sha, manifest_sha, backend, pins):
    expected = {"schema": "expanded_D2_candidate_evaluation_v1", "complete": True,
                "registration_sha256": reg_sha, "candidate_update": update,
                "checkpoint_sha256": pins[update], "cohort_name": "ranking",
                "cohort_sha256": cohort_sha, "episodes": 1024}
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError("candidate result identity mismatch: " + key)
    model_pin = result.get("model_state_dict_sha256")
    if not isinstance(model_pin, str) or len(model_pin) != 64:
        raise ValueError("candidate model-state hash invalid")
    if result.get("backend") != backend:
        raise ValueError("candidate backend differs from registration runtime")
    rows = result.get("rows")
    if not isinstance(rows, list) or result.get("episodes") != len(rows):
        raise ValueError("candidate episode count differs from rows")
    if result.get("episodes") != 1024:
        raise ValueError("candidate must contain exactly 1024 episodes")
    values = [_row_alive(row, i) for i, row in enumerate(rows)]
    metrics = _metrics(values)
    _check_metrics(result.get("performance"), metrics, "result")
    if result.get("caps") != sum(row["truncated"] for row in rows):
        raise ValueError("candidate cap count mismatch")
    deaths = [row for row in rows if row["terminated"]]
    death_causes = {cause: 0 for cause in DEATH_CAUSES}
    for row in deaths:
        cause = row.get("death_cause")
        death_causes[cause] += 1
    if result.get("death_causes") != death_causes:
        raise ValueError("candidate death cause counts mismatch")
    elapsed = _finite(result.get("elapsed_seconds"), "elapsed_seconds")
    if elapsed <= 0:
        raise ValueError("elapsed_seconds must be positive")
    return metrics


def _load_registration(path, pin):
    reg = read_pinned(path, pin, "ranking registration")
    if reg.get("schema") != "expanded_D2_evaluation_registration_v1" or reg.get("mode") != "ranking":
        raise ValueError("ranking registration schema/mode mismatch")
    source = reg.get("source", {})
    evaluator = source.get("evaluator_sha256")
    if not isinstance(evaluator, str) or len(evaluator) != 64:
        raise ValueError("registration evaluator pin missing")
    cohort = reg.get("cohorts", {}).get("ranking", {})
    manifest_path, manifest_sha = cohort.get("manifest_path"), cohort.get("manifest_sha256")
    manifest = read_pinned(manifest_path, manifest_sha, "ranking manifest")
    seeds = manifest.get("seeds")
    if manifest.get("count") != 1024 or seeds != list(SEEDS) or cohort.get("count") != 1024:
        raise ValueError("registered ranking manifest differs from exact cohort")
    return reg, evaluator, runtime_digest(reg), manifest_sha


def produce_selection(registration_path, registration_sha256, summary_path,
                      summary_sha256, outer_receipt_path, outer_receipt_sha256,
                      result_bindings, output_path):
    """Consume pinned R5 registration, ranking bundle, outer receipt, and six result artifacts.

    result_bindings maps integer update to (absolute path, SHA-256).
    """
    reg, evaluator_sha, runtime_sha, manifest_sha = _load_registration(
        registration_path, registration_sha256)
    summary = read_pinned(summary_path, summary_sha256, "ranking summary")
    outer = read_pinned(outer_receipt_path, outer_receipt_sha256, "outer receipt")
    run_id = reg.get("run_id")
    if not run_id or summary.get("schema") != RANKING_SCHEMA or summary.get("selection_only") is not True:
        raise ValueError("ranking summary schema/status invalid")
    if outer.get("schema") != "expanded_eval_outer_receipt_v1" or any(
        (outer.get("raw_exit_code") != 0, outer.get("stop_reason") is not None,
         outer.get("process_group_absent") is not True, outer.get("stage") != "ranking",
         outer.get("candidate_update") != 348, outer.get("cohort") != "ranking",
         outer.get("run_id") != run_id,
         outer.get("registration_sha256") != registration_sha256,
         outer.get("evaluator_sha256") != evaluator_sha)):
        raise ValueError("outer receipt failed ranking identity/postflight")
    worker_pin = reg["source"].get("worker_sha256")
    if outer.get("worker_sha256") != worker_pin:
        raise ValueError("outer receipt worker pin differs from registration")
    pins = _pins(reg)
    if not isinstance(result_bindings, dict) or set(result_bindings) != set(UPDATES):
        raise ValueError("exact six externally pinned result bindings required")
    summaries = summary.get("candidate_results")
    if not isinstance(summaries, list) or len(summaries) != 6:
        raise ValueError("ranking summary must contain six candidates")
    by_update = {}
    for item in summaries:
        update = item.get("candidate_update")
        if type(update) is not int or update in by_update:
            raise ValueError("duplicate/invalid candidate in summary")
        by_update[update] = item
    if set(by_update) != set(UPDATES):
        raise ValueError("ranking summary candidate set mismatch")
    artifacts = outer.get("output_artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("outer output_artifacts missing")
    artifact_pins = {(item.get("path"), item.get("sha256")) for item in artifacts}
    if (str(Path(summary_path).resolve()), summary_sha256) not in artifact_pins:
        raise ValueError("outer receipt does not bind ranking summary")
    refs, means = [], {}
    for update in UPDATES:
        path, pin = result_bindings[update]
        path = str(Path(path).resolve())
        if (path, pin) not in artifact_pins:
            raise ValueError("outer receipt does not bind candidate result " + str(update))
        result = read_pinned(path, pin, "candidate result")
        metrics = _validate_result(result, update, registration_sha256, evaluator_sha,
                                   runtime_sha, reg["cohorts"]["ranking"]["manifest_sha256"],
                                   manifest_sha, reg["runtime"].get("backend"), pins)
        # R5 summary embeds each complete candidate result. Require exact semantic equality.
        if by_update[update] != result:
            raise ValueError("ranking summary candidate differs from pinned result")
        means[update] = metrics["mean"]
        refs.append({"path": path, "sha256": pin})
    winner = min(UPDATES, key=lambda u: (-means[u], u))
    if summary.get("winner_update") != winner:
        raise ValueError("ranking summary winner differs from row argmax")
    record = {"schema": "expanded_D2_selection_record_v2", "winner_update": winner,
              "winner_checkpoint_sha256": pins[winner],
              "incumbent_checkpoint_sha256": pins[348], "ranking_results": refs,
              "ranking_registration_path": str(Path(registration_path).resolve()),
              "ranking_registration_sha256": registration_sha256,
              "ranking_run_id": run_id, "evaluator_sha256": evaluator_sha,
              "runtime_member_map_sha256": runtime_sha,
              "ranking_manifest_path": str(Path(reg["cohorts"]["ranking"]["manifest_path"]).resolve()),
              "ranking_manifest_sha256": manifest_sha,
              "ranking_mean_alive_frames": means[winner],
              "ranking_metric": "mean_alive_frames_all_1024_including_caps",
              "confirmation_status": "no_confirmation" if winner == 348 else "eligible_for_parent_confirmation_gate",
              "evidence_limit": "selection preparation only; does not alter accepted update 348 or authorize confirmation"}
    if winner == 348:
        record["invocable_confirmation_record"] = False
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as f:
        json.dump(record, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")
        f.flush()
    return record


def validate_selection_record(record_path, record_sha256, ranking_registration_path,
                              ranking_registration_sha256, result_bindings):
    """Future confirmation-side pure validator with registration hash externally bound."""
    record = read_pinned(record_path, record_sha256, "selection record")
    if record.get("ranking_registration_path") != str(Path(ranking_registration_path).resolve()) or \
       record.get("ranking_registration_sha256") != ranking_registration_sha256:
        raise ValueError("selection ranking registration binding mismatch")
    reg, evaluator_sha, runtime_sha, manifest_sha = _load_registration(
        ranking_registration_path, ranking_registration_sha256)
    expected_manifest_path = str(Path(reg["cohorts"]["ranking"]["manifest_path"]).resolve())
    if record.get("ranking_run_id") != reg.get("run_id") or record.get("evaluator_sha256") != evaluator_sha or \
       record.get("runtime_member_map_sha256") != runtime_sha or record.get("ranking_manifest_sha256") != manifest_sha or \
       record.get("ranking_manifest_path") != expected_manifest_path:
        raise ValueError("selection provenance mismatch")
    pins = _pins(reg)
    if set(result_bindings) != set(UPDATES) or len(record.get("ranking_results", [])) != 6:
        raise ValueError("six externally pinned result bindings required")
    means = {}
    refs = []
    for update in UPDATES:
        path, pin = result_bindings[update]
        path = str(Path(path).resolve())
        result = read_pinned(path, pin, "candidate result")
        metrics = _validate_result(result, update, ranking_registration_sha256,
                                   evaluator_sha, runtime_sha, reg["cohorts"]["ranking"]["manifest_sha256"],
                                   manifest_sha, reg["runtime"].get("backend"), pins)
        means[update] = metrics["mean"]
        refs.append({"path": path, "sha256": pin})
    winner = min(UPDATES, key=lambda u: (-means[u], u))
    if record.get("ranking_results") != refs or record.get("winner_update") != winner:
        raise ValueError("selection refs/winner differ from pinned ranking results")
    if record.get("winner_checkpoint_sha256") != pins[winner] or record.get("incumbent_checkpoint_sha256") != pins[348]:
        raise ValueError("selection checkpoint pin mismatch")
    if record.get("ranking_mean_alive_frames") != means[winner]:
        raise ValueError("selection winner metric mismatch")
    if winner == 348 and (record.get("confirmation_status") != "no_confirmation" or record.get("invocable_confirmation_record") is not False):
        raise ValueError("348 winner must leave confirmation unopened")
    if winner != 348 and record.get("confirmation_status") != "eligible_for_parent_confirmation_gate":
        raise ValueError("confirmation gate status invalid")
    return record
