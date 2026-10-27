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
import sys
import time

EXPECTED_SCHEMA = "d2_normal_training_parent_terminal_receipt_v1"
EXPECTED_STATUS = "accepted_completed_normal_training_iteration"
EXPECTED_REGISTRATION_SCHEMA = "d2_training_v3_continuation_registration_v1"


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
    bindings = {
        "checkpoint_sha256": parent.get("sha256"),
        "registration_sha256": parent.get("registration_sha256"),
        "phase": parent.get("phase"),
        "completed_phase_updates": parent.get("completed_updates"),
        "runtime_sha256": registration.get("runtime_sha256"),
        "policy_sha256": registration.get("policy_sha256"),
    }
    # This adapter accepts same-phase D2 parents only. Receipt identity and
    # counters remain receipt-owned; paths and registered hashes bind them.
    require(receipt.get("checkpoint_sha256") == bindings["checkpoint_sha256"],
            "Accepted checkpoint digest differs")
    require(receipt.get("registration_sha256") == bindings["registration_sha256"],
            "Accepted parent registration digest differs")
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
    require(type(iteration_wall) in (int, float) and math.isfinite(iteration_wall)
            and iteration_wall > 0 and wall >= iteration_wall
            and type(checkpoint_wall) in (int, float) and math.isfinite(checkpoint_wall)
            and 0 < checkpoint_wall <= iteration_wall
            and isinstance(receipt.get("cumulative_wall_scope"), str)
            and receipt["cumulative_wall_scope"],
            "Accepted parent complete outer-wall accounting differs")
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


def summarize_evaluation(path: Path) -> dict:
    """Summarize one explicit frozen evaluation JSON without changing authority."""
    data = load_json(path)
    evaluation = data.get("evaluation")
    require(isinstance(evaluation, dict) and evaluation.get("complete") is True,
            "Evaluation is missing or incomplete")
    require(evaluation.get("episodes") == 64 and isinstance(evaluation.get("rows"), list),
            "Evaluation must contain 64 episode rows")
    summary = summarize_performance(evaluation["rows"])
    causes = evaluation.get("death_causes")
    require(isinstance(causes, dict), "Evaluation death counts are missing")
    deaths = {}
    for cause in DEATH_CAUSES:
        count = causes.get(cause, 0)
        require(type(count) is int and count >= 0, "Evaluation death count is invalid")
        deaths[cause] = count
    require(sum(deaths.values()) == evaluation.get("deaths") == 64,
            "Evaluation death counts do not account for all episodes")
    return {
        "checkpoint": data.get("checkpoint", "unknown"),
        "phase_update": data.get("phase_update"),
        "summary": summary,
        "deaths": deaths,
        "source": str(path),
    }


def markdown_report(best_path: Path, latest_path: Path) -> str:
    """Render one Markdown table; labels come only from explicit input options."""
    best = summarize_evaluation(best_path)
    latest = summarize_evaluation(latest_path)
    lines = [
        "| Designation | Checkpoint | Q1 tail mean | Q4 tail mean | Mean alive frames | Death counts (normal, kamikaze, explosion, moving, static) |",
        "|---|---|---:|---:|---:|---|",
    ]
    for label, record in (("BEST REFERENCE", best), ("LATEST", latest)):
        s = record["summary"]
        d = record["deaths"]
        death_text = ", ".join(str(d[k]) for k in DEATH_CAUSES)
        lines.append(
            f"| {label} (phase {record['phase_update']}) | {record['checkpoint']} | "
            f"{s['Q1']:.4f} | {s['Q4']:.4f} | {s['mean']:.6f} | {death_text} |"
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
