"""Read-only authority inspector and canonical D2 performance summarizer.

This is preparation tooling, not a controller or launch adapter. Callers must
externally pin both the accepted parent receipt and registration digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

EXPECTED_SCHEMA = "d2_normal_training_parent_terminal_receipt_v1"
EXPECTED_STATUS = "accepted_completed_normal_training_iteration"
EXPECTED_REGISTRATION_SCHEMA = "d2_training_v3_continuation_registration_v1"
PIN_FIELDS = ("checkpoint_sha256", "registration_sha256", "runtime_sha256", "policy_sha256")
EVALUATION_SEEDS_START = 0xD0000000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_sha256(value, name: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None,
            f"{name} must be a 64-character SHA256 hex string")
    return value.lower()


def validate_authority(receipt: dict, registration: dict,
                       receipt_sha: str, registration_sha: str) -> dict:
    """Bind accepted parent authority without accepting metadata overrides."""
    require(receipt.get("schema") == EXPECTED_SCHEMA, "Parent receipt schema differs")
    require(receipt.get("status") == EXPECTED_STATUS, "Parent receipt is not accepted")
    require(receipt.get("training_continuation_eligible") is True
            and receipt.get("stage_promotion_eligible") is False
            and receipt.get("competence_passed") is False
            and receipt.get("checkpoint_metadata_edited") is False,
            "Receipt continuation authority differs")
    require(receipt.get("publication_failure_present") is False
            and receipt.get("raw_outer_exit") == 0 and receipt.get("raw_worker_exit") == 0
            and receipt.get("cancellation_lineage") == [],
            "Receipt execution did not complete cleanly")
    require(registration.get("schema") == EXPECTED_REGISTRATION_SCHEMA,
            "Registration schema differs")
    require(registration.get("normal_training_iteration") is True
            and registration.get("training_eligible") is False,
            "Registration eligibility flags differ")

    parent = registration.get("parent")
    require(isinstance(parent, dict), "Registration parent authority is missing")
    registration_pins = {
        "checkpoint_sha256": parent.get("sha256"),
        "registration_sha256": parent.get("registration_sha256"),
        "runtime_sha256": registration.get("runtime_sha256"),
        "policy_sha256": registration.get("policy_sha256"),
    }
    receipt_pins = {key: receipt.get(key) for key in PIN_FIELDS}
    for key in PIN_FIELDS:
        require_sha256(receipt_pins[key], f"Receipt {key}")
        require_sha256(registration_pins[key], f"Registration {key}")
        require(receipt_pins[key].lower() == registration_pins[key].lower(),
                f"Accepted {key.replace('_sha256', ' digest').replace('_', ' ')} differs")
    bindings = {
        "checkpoint_sha256": registration_pins["checkpoint_sha256"],
        "registration_sha256": registration_pins["registration_sha256"],
        "phase": parent.get("phase"),
        "completed_phase_updates": parent.get("completed_updates"),
        "runtime_sha256": registration.get("runtime_sha256"),
        "policy_sha256": registration.get("policy_sha256"),
    }
    # This adapter accepts same-phase D2 parents only. Receipt identity and
    # counters remain receipt-owned; paths and registered hashes bind them.
    require(receipt.get("phase") == bindings["phase"] == "D2"
            and type(receipt.get("completed_phase_updates")) is int
            and receipt.get("completed_phase_updates") == bindings["completed_phase_updates"],
            "Accepted parent phase or cumulative update differs")
    checkpoint_path = Path(receipt.get("checkpoint_path", ""))
    require(checkpoint_path.is_absolute()
            and str(checkpoint_path) == str(Path(parent.get("path", "")).resolve())
            and checkpoint_path.parent.name == receipt.get("run_id"),
            "Accepted parent run identity or checkpoint path differs")
    local = receipt.get("completed_local_updates")
    counters = receipt.get("cumulative_counters")
    next_indices = receipt.get("next_episode_indices")
    new_counters = receipt.get("new_counters")
    require(type(local) is int and local > 0
            and isinstance(counters, dict) and isinstance(new_counters, dict)
            and all(type(counters.get(key)) is int and counters[key] >= 0
                    for key in ("updates", "optimizer_steps", "environment_decisions", "raw_frames"))
            and counters["updates"] >= local and new_counters.get("updates") == local,
            "Accepted parent local or cumulative counters differ")
    require(isinstance(next_indices, list) and len(next_indices) == 64
            and all(type(index) is int and index >= 0 for index in next_indices),
            "Accepted parent next episode indices differ")
    wall = receipt.get("cumulative_D2_inclusive_wall_seconds")
    require(type(wall) in (int, float) and math.isfinite(wall) and wall > 0,
            "Accepted parent inclusive outer wall differs")
    iteration_wall = receipt.get("inclusive_iteration_wall_seconds")
    checkpoint_wall = receipt.get("checkpoint_recorded_work_wall_seconds")
    require(isinstance(receipt.get("cumulative_wall_scope"), str)
            and receipt["cumulative_wall_scope"],
            "Accepted parent outer-wall scope is missing")
    if iteration_wall is not None:
        require(type(iteration_wall) in (int, float) and math.isfinite(iteration_wall)
                and iteration_wall > 0 and wall >= iteration_wall,
                "Optional iteration wall timing is invalid")
    if checkpoint_wall is not None:
        require(type(checkpoint_wall) in (int, float) and math.isfinite(checkpoint_wall)
                and checkpoint_wall > 0
                and (iteration_wall is None or checkpoint_wall <= iteration_wall),
                "Optional checkpoint-local timing is invalid")
    require(receipt.get("runtime_sha256") == bindings["runtime_sha256"]
            and receipt.get("policy_sha256") == bindings["policy_sha256"],
            "Accepted parent runtime or policy differs")
    require(registration.get("parent", {}).get("terminal_receipt_sha256") == receipt_sha,
            "Registration does not pin this accepted receipt")
    require(registration.get("parent", {}).get("terminal_receipt_path") == receipt.get("_path"),
            "Registration receipt path differs")
    return {
        "parent_run_id": receipt["run_id"],
        "phase": receipt["phase"],
        "phase_updates": receipt["completed_phase_updates"],
        "local_updates": receipt["completed_local_updates"],
        "cumulative_counters": receipt["cumulative_counters"],
        "inclusive_outer_wall_seconds": receipt["cumulative_D2_inclusive_wall_seconds"],
        "next_episode_indices": receipt["next_episode_indices"],
        "checkpoint_sha256": receipt["checkpoint_sha256"],
        "registration_sha256": receipt["registration_sha256"],
        "runtime_sha256": receipt["runtime_sha256"],
        "policy_sha256": receipt["policy_sha256"],
    }


def summarize_performance(rows: list[dict], *, metric: str = "alive_frames",
                          expected_count: int = 64) -> dict:
    """Return mean and sorted bottom/top-quartile means, independent of row order."""
    require(type(expected_count) is int and expected_count >= 2,
            "Expected episode count must be an integer >= 2")
    require(len(rows) == expected_count, "Performance cohort size differs")
    values = []
    for row in rows:
        value = row.get(metric)
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                "Alive-frame value must be finite and nonnegative")
        values.append(float(value))
    ordered = sorted(values)
    tail = expected_count // 4
    require(tail > 0, "Performance cohort is too small")
    return {
        "Q1": sum(ordered[:tail]) / tail,
        "Q4": sum(ordered[-tail:]) / tail,
        "mean": sum(ordered) / expected_count,
        "episodes": expected_count,
        "metric": metric,
        "quantile_method": "sorted_bottom_top_quartile_means",
    }


DEATH_CAUSES = (
    "normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
    "moving_pattern_rect", "static_pattern_rect",
)
ALL_CAUSES = DEATH_CAUSES + ("unknown", "unavailable")


def _check_embedded_summary(data: dict, evaluation: dict, summary: dict,
                            rows: list[dict]) -> None:
    for container, key, metric in ((data, "performance", "alive_frames"),
                                   (data, "performance", "score")):
        embedded = container.get(key)
        if embedded is not None and metric in embedded:
            require(isinstance(embedded, dict) and isinstance(embedded[metric], dict),
                    f"Embedded {metric} performance is malformed")
            observed = embedded[metric]
            actual = summarize_performance(rows, metric=metric)
            for field in ("Q1", "Q4", "mean"):
                value = observed.get(field)
                require(type(value) in (int, float) and math.isfinite(value)
                        and value == actual[field],
                        f"Embedded {metric} {field} differs from evaluation rows")
    for container, field, metric in ((data, "mean_alive_frames", "alive_frames"),
                                     (evaluation, "mean_alive_frames", "alive_frames"),
                                     (evaluation, "mean_score", "score")):
        if field in container:
            actual = summarize_performance(rows, metric=metric)["mean"]
            value = container[field]
            require(type(value) in (int, float) and math.isfinite(value) and value == actual,
                    f"Embedded {field} differs from evaluation rows")


def summarize_evaluation(path: Path) -> dict:
    """Summarize one explicit frozen evaluation JSON without changing authority."""
    data = load_json(path)
    evaluation = data.get("evaluation")
    require(isinstance(evaluation, dict) and evaluation.get("complete") is True,
            "Evaluation is missing or incomplete")
    require(evaluation.get("episodes") == 64 and isinstance(evaluation.get("rows"), list),
            "Evaluation must contain 64 episode rows")
    rows = evaluation["rows"]
    require(len(rows) == 64, "Evaluation must contain 64 episode rows")
    indices, seeds = set(), set()
    row_causes = {cause: 0 for cause in ALL_CAUSES}
    caps = deaths = 0
    for row in rows:
        require(isinstance(row, dict), "Evaluation row is malformed")
        index, seed = row.get("episode_index"), row.get("seed")
        require(type(index) is int and 0 <= index < 64,
                "Evaluation episode index is outside D2 cohort")
        require(type(seed) is int and seed == EVALUATION_SEEDS_START + index,
                "Evaluation seed does not bind to D2 episode index")
        require(index not in indices and seed not in seeds,
                "Evaluation contains duplicate episode index or seed")
        indices.add(index)
        seeds.add(seed)
        cause = row.get("death_cause")
        terminated, truncated = row.get("terminated"), row.get("truncated")
        require(type(terminated) is bool and type(truncated) is bool
                and terminated != truncated,
                "Evaluation termination and truncation flags are inconsistent")
        if terminated:
            require(cause in ALL_CAUSES, "Terminated evaluation row has invalid death cause")
            deaths += 1
            row_causes[cause] += 1
        else:
            require(cause in (None, "cap", "capped"),
                    "Truncated evaluation row has invalid censored cause")
            caps += 1
    require(indices == set(range(64)) and seeds == set(range(EVALUATION_SEEDS_START,
                                                              EVALUATION_SEEDS_START + 64)),
            "Evaluation does not contain the complete D2 cohort")
    summary = summarize_performance(rows)
    _check_embedded_summary(data, evaluation, summary, rows)
    causes = evaluation.get("death_causes")
    require(isinstance(causes, dict), "Evaluation death counts are missing")
    reported_causes = {}
    for cause in ALL_CAUSES:
        count = causes.get(cause, 0)
        require(type(count) is int and count >= 0, "Evaluation death count is invalid")
        reported_causes[cause] = count
    require(reported_causes == row_causes,
            "Evaluation row causes differ from aggregate death causes")
    require(type(evaluation.get("deaths")) is int and evaluation["deaths"] == deaths,
            "Evaluation death total differs from rows")
    require(type(evaluation.get("caps")) is int and evaluation["caps"] == caps,
            "Evaluation cap total differs from rows")
    return {
        "checkpoint": data.get("checkpoint", "unknown"),
        "phase_update": data.get("phase_update"),
        "summary": summary,
        "deaths": {cause: row_causes[cause] for cause in DEATH_CAUSES},
        "unknown": row_causes["unknown"],
        "unavailable": row_causes["unavailable"],
        "caps": caps,
        "source": str(path),
    }


def markdown_report(best_path: Path, latest_path: Path) -> str:
    """Render one Markdown table; labels come only from explicit input options."""
    best = summarize_evaluation(best_path)
    latest = summarize_evaluation(latest_path)
    lines = [
        "| Designation | Checkpoint | Q1 tail mean | Q4 tail mean | Mean alive frames | Death counts (normal, kamikaze, explosion, moving, static) | Caps | Unknown | Unavailable |",
        "|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for label, record in (("BEST REFERENCE", best), ("LATEST", latest)):
        s = record["summary"]
        d = record["deaths"]
        death_text = ", ".join(str(d[k]) for k in DEATH_CAUSES)
        lines.append(
            f"| {label} (phase {record['phase_update']}) | {record['checkpoint']} | "
            f"{s['Q1']:.4f} | {s['Q4']:.4f} | {s['mean']:.6f} | {death_text} | "
            f"{record['caps']} | {record['unknown']} | {record['unavailable']} |"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only D2 authority preflight and report")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="validate externally pinned parent authority")
    inspect.add_argument("--receipt", required=True, type=Path)
    inspect.add_argument("--receipt-sha256", required=True)
    inspect.add_argument("--registration", required=True, type=Path)
    inspect.add_argument("--registration-sha256", required=True)
    inspect.add_argument("--output", required=True, type=Path)
    report = subparsers.add_parser("report", help="report two explicit frozen evaluations")
    report.add_argument("--best-reference", required=True, type=Path)
    report.add_argument("--latest", required=True, type=Path)
    args = parser.parse_args(argv)
    started = time.monotonic()
    if args.command == "report":
        best_path = args.best_reference.resolve(strict=True)
        latest_path = args.latest.resolve(strict=True)
        require(best_path.is_absolute() and latest_path.is_absolute(),
                "Evaluation paths must be absolute")
        print(markdown_report(best_path, latest_path))
        return 0
    receipt_path = args.receipt.resolve(strict=True)
    registration_path = args.registration.resolve(strict=True)
    require(receipt_path.is_absolute() and registration_path.is_absolute()
            and args.output.is_absolute(), "Authority and output paths must be absolute")
    require_sha256(args.receipt_sha256, "External receipt digest")
    require_sha256(args.registration_sha256, "External registration digest")
    require(sha256(receipt_path) == args.receipt_sha256,
            "Accepted receipt differs from external digest")
    require(sha256(registration_path) == args.registration_sha256,
            "Registration differs from external digest")
    receipt = load_json(receipt_path)
    receipt["_path"] = str(receipt_path)
    registration = load_json(registration_path)
    authority = validate_authority(receipt, registration,
                                   args.receipt_sha256, args.registration_sha256)
    manifest = {
        "schema": "d2_continuation_preparation_manifest_v1",
        "preparation_only": True,
        "inspection_limits": {
            "receipt_and_registration_byte_digests_checked": True,
            "declared_field_consistency_checked": True,
            "checkpoint_weights_hashed": False,
            "next_indices_verified_against_decoded_state": False,
            "resources_or_outer_timings_independently_proven": False,
            "outer_wall_authority": "externally supplied accepted receipt cumulative_D2_inclusive_wall_seconds",
            "execution_preflight_replaced": False,
        },
        "parent_authority": authority,
        "anchors": {
            "receipt_path": str(receipt_path),
            "receipt_sha256": args.receipt_sha256,
            "registration_path": str(registration_path),
            "registration_sha256": args.registration_sha256,
            "controller_path": str(Path(__file__).resolve()),
            "controller_sha256": sha256(Path(__file__).resolve()),
        },
        "created_monotonic_elapsed_seconds": time.monotonic() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"manifest": str(args.output), "manifest_sha256": sha256(args.output),
                      "cwd": os.getcwd(), "python": sys.executable,
                      "elapsed_seconds": time.monotonic() - started}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
