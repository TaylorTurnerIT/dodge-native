"""Successor expanded D2 evaluator. Import is inert; evaluate_registered is production-only."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
PROPOSAL = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json")
PROPOSAL_SHA256 = "187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765"
INCUMBENT_RECEIPT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json")
INCUMBENT_RECEIPT_SHA256 = "cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016"
INCUMBENT_UPDATE = 348
INCUMBENT_CHECKPOINT_SHA256 = "b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369"
RUNTIME_ROOT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime")
PROTOCOL_PATH = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/docs/v2-m3-run-protocol.json")
PROTOCOL_SHA256 = "9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab"
SEED_PROOF_PATH = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-seed-lineage-parent-validation-20261026-r5/receipt.json")
SEED_PROOF_SHA256 = "fe4b0cc6cbbc4b9ff4335c4462dbc120954f1bac0bac8c6c761d5c18636c0949"
BENCHMARK_MANIFEST = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-eval-parent-integration-20261026-r1/benchmark-dev64-seed-manifest.json")
BENCHMARK_MANIFEST_SHA256 = "a57410e1848f8b35b874507afa21a4d90ced706efd3bd7a141e1dc3ad5df3695"
INCUMBENT_GOLDEN_ROWS = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-lr-20261026-r1/development-000348.jsonl")
INCUMBENT_GOLDEN_ROWS_SHA256 = "d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03"
NATIVE_RELATIVE_PATH = "dodge_rl/_native.cpython-312-darwin.so"
NATIVE_SHA256 = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
RUNTIME_MEMBERS = {
    "dodge_rl/__init__.py": "2bf56a8151b512d78a228d604fdac67c529c8ebfd3fa233c71c2dd4f882b44dc",
    "dodge_rl/_native.cpython-312-darwin.so": NATIVE_SHA256,
    "dodge_rl/checkpoints.py": "807141943a742c6e9fdd34274c191b3c318134cc7fb0c1c6256874cadee1cbc3",
    "dodge_rl/critic_diagnostics.py": "272059f7c12ebe30e36dc6e9e2388c5b088c11bcd002ee95478459a61e452dbe",
    "dodge_rl/dev_eval.py": "eecf71936f10938169c0283ed1bb0717b87e46da7ee4ac8636a20d366df3753b",
    "dodge_rl/gradient_alignment.py": "cd7d16aebe9eed247b0a4747956d8106991b3637ab0b45118ea9e7ebc0c1e25f",
    "dodge_rl/identity.py": "50775b2e7c30e53757dd3134d11613f716733cee8e6a96cc18b62e8ff2a4a053",
    "dodge_rl/models/__init__.py": "b28b2623443e31d9e9cb81350f89e9fb7d285abe3e2a74c007be8e4cfff432dc",
    "dodge_rl/models/teacher.py": "e4d7f597a2824c2b0d4ba261dddc9d7d1ee1d5592c2fc966a44c54b5ec417e35",
    "dodge_rl/ppo.py": "b3cef91b1293056e9d1820a94fd5730accae4c5728d23566857a6c3a0e1eeac5",
    "dodge_rl/supervision.py": "45a5714d70d956371442cc3b5ebd1d56d5c498658296afa7e9c9d4c13f2a9b70",
    "dodge_rl/survival_gate.py": "11257111602f26e49fbc71afc6a51acb79434a3717bd8d6d36d1bbf87dfb8841",
    "dodge_rl/train_teacher.py": "1d134bfb221ff52139e1243c9e4f9c3063432942a3274c567b71db4d7669c0cf",
}
DEATH_CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
                "static_pattern_rect", "moving_pattern_rect", "unknown", "unavailable")
COHORT_KEYS = {
    "benchmark_dev64": ("benchmark_dev64",),
    "ranking": ("ranking",),
    "confirmation": ("confirmation",),
}
CANDIDATE_UPDATES = (180, 204, 276, 300, 324, 348)
RECEIPT_STATUSES = {"accepted_complete_candidate_from_completed_normal_training_iteration",
                    "accepted_completed_normal_training_iteration"}
_BACKEND_IDENTITY = None


class ValidationError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _absolute(path: object, name: str) -> Path:
    _require(type(path) is str and Path(path).is_absolute(), f"{name} must be absolute")
    return Path(path).resolve()


def _validate_seed_vector(cohort_name: str, manifest: dict, seeds: list[int]) -> None:
    _require(type(seeds) is list and len(seeds) > 0 and len(seeds) % 4 == 0,
             "cohort must have positive N divisible by four")
    _require(all(type(seed) is int and 0 <= seed <= 0xffffffff for seed in seeds)
             and len(set(seeds)) == len(seeds), "cohort seeds invalid or duplicated")
    _require(seeds == list(range(seeds[0], seeds[0] + len(seeds))), "cohort seeds reordered or outside registered range")
    if cohort_name == "benchmark_dev64":
        _require(seeds == list(range(0xD0000000, 0xD0000040)), "benchmark seed vector differs")
        return
    protocol = json.loads(PROTOCOL_PATH.read_bytes())
    for low, high in protocol["training_excluded_ranges"]:
        _require(not any(low <= seed <= high for seed in seeds), "new cohort overlaps excluded B/E or D128 seeds")
    proof_raw = SEED_PROOF_PATH.read_bytes()
    _require(_sha(proof_raw) == SEED_PROOF_SHA256, "parent seed-lineage proof bytes differ")
    proof = json.loads(proof_raw)
    _require(proof.get("schema") == "expanded_seed_parent_checkpoint_validation_v1"
             and proof.get("status") == "passed"
             and proof.get("CPU_checkpoint_payloads_read") == 10
             and proof.get("conservative_unique_seed_count") == 110911
             and proof.get("no_games_or_training_or_MPS") is True,
             "parent seed-lineage proof identity differs")
    _require(all(value == [] for value in proof["collisions"].values()), "parent seed-lineage proof reports collision")


def _validate_static(registration_path: str, registration_sha256: str,
                     candidate_update: int, cohort_name: str, output_path: str):
    """Validate every public pin and cohort before imports, guard, constructors, or checkpoint reads."""
    _require(type(candidate_update) is int and candidate_update in CANDIDATE_UPDATES,
             "candidate update is not one of the six registered candidates")
    _require(cohort_name in COHORT_KEYS, "cohort name is not registered")
    reg_path = _absolute(registration_path, "registration_path")
    raw = reg_path.read_bytes()
    _require(_sha(raw) == registration_sha256, "registration byte SHA-256 differs")
    reg = json.loads(raw)
    required = {"schema", "run_id", "mode", "source", "runtime", "candidates", "cohorts",
                "selection_record", "limits", "output_dir", "cancel_path", "one_shot_marker",
                "state_path", "expected_lease", "review_records", "benchmark_reference"}
    _require(type(reg) is dict and set(reg) == required, "registration top-level field set differs")
    _require(reg.get("schema") == "expanded_D2_evaluation_registration_v1", "registration schema differs")
    _require(type(reg.get("run_id")) is str and reg["run_id"].strip(), "run_id missing")
    source = reg["source"]
    _require(type(source) is dict and set(source) == {"evaluator_path", "evaluator_sha256", "worker_path",
             "worker_sha256", "launcher_path", "launcher_sha256"}, "source pin fields differ")
    _require(_absolute(source["evaluator_path"], "evaluator_path") == Path(__file__).resolve(),
             "evaluator source path differs")
    _require(source["evaluator_sha256"] == _file_sha(Path(__file__)), "evaluator source bytes differ")
    for name in ("worker", "launcher"):
        p = _absolute(source[f"{name}_path"], f"{name}_path")
        _require(type(source[f"{name}_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", source[f"{name}_sha256"]),
                 f"{name} SHA pin invalid")
        _require(p.is_file() and _file_sha(p) == source[f"{name}_sha256"], f"{name} source bytes differ")
    runtime = reg["runtime"]
    _require(type(runtime) is dict and set(runtime) == {"root", "member_sha256", "native_relative_path",
             "backend", "torch_version", "numpy_version", "pycache_prefix"}, "runtime pin fields differ")
    root = _absolute(runtime["root"], "runtime root")
    _require(root == RUNTIME_ROOT.resolve() and runtime["member_sha256"] == RUNTIME_MEMBERS,
             "runtime root or full member map differs")
    _require(runtime["native_relative_path"] == NATIVE_RELATIVE_PATH, "native relative path differs")
    for relative, expected in RUNTIME_MEMBERS.items():
        file = (root / relative).resolve()
        _require(file.is_relative_to(root) and file.is_file() and _file_sha(file) == expected,
                 f"runtime member differs: {relative}")
    _require(runtime.get("backend") in ("cpu", "mps"), "runtime backend must be pinned CPU or MPS")
    for field in ("torch_version", "numpy_version"):
        _require(type(runtime.get(field)) is str and runtime[field], f"runtime {field} missing")
    _require(runtime.get("pycache_prefix") is None or type(runtime.get("pycache_prefix")) is str,
             "runtime pycache_prefix must match Python's value")
    proposal_raw = PROPOSAL.read_bytes()
    _require(_sha(proposal_raw) == PROPOSAL_SHA256, "frozen proposal source bytes differ")
    protocol_raw = PROTOCOL_PATH.read_bytes()
    _require(_sha(protocol_raw) == PROTOCOL_SHA256, "frozen evaluation protocol bytes differ")
    seed_proof_raw = SEED_PROOF_PATH.read_bytes()
    _require(_sha(seed_proof_raw) == SEED_PROOF_SHA256, "parent seed-lineage proof bytes differ")
    proposal = json.loads(proposal_raw)
    _require(type(reg["candidates"]) is dict and set(reg["candidates"]) == {str(x) for x in CANDIDATE_UPDATES},
             "candidate registration keys differ")
    proposal_by_update = {str(item["phase_update"]): item for item in proposal["candidates"]}
    for update in CANDIDATE_UPDATES:
        key = str(update); entry = reg["candidates"][key]; pin = proposal_by_update[key]
        _require(type(entry) is dict and entry.get("checkpoint_path") == pin["checkpoint_path"]
                 and entry.get("checkpoint_sha256") == pin["checkpoint_sha256"]
                 and entry.get("phase_update") == update
                 and entry.get("source_receipt_path") == pin["source_receipt_path"]
                 and entry.get("source_receipt_sha256") == pin["source_receipt_sha256"],
                 f"candidate {update} differs from frozen proposal")
        cp = _absolute(entry["checkpoint_path"], f"candidate {update} checkpoint")
        receipt = _absolute(entry["source_receipt_path"], f"candidate {update} receipt")
        _require(cp.is_file() and _file_sha(cp) == entry["checkpoint_sha256"], f"candidate {update} checkpoint bytes differ")
        receipt_raw = receipt.read_bytes()
        _require(_sha(receipt_raw) == entry["source_receipt_sha256"], f"candidate {update} receipt bytes differ")
        receipt_obj = json.loads(receipt_raw)
        _require(receipt_obj.get("status") in RECEIPT_STATUSES
                 and receipt_obj.get("checkpoint_sha256") == entry["checkpoint_sha256"]
                 and Path(receipt_obj.get("checkpoint_path", "")).resolve() == cp,
                 f"candidate {update} accepted receipt identity differs")
    incumbent_raw = INCUMBENT_RECEIPT.read_bytes()
    _require(_sha(incumbent_raw) == INCUMBENT_RECEIPT_SHA256, "accepted incumbent receipt bytes differ")
    incumbent = json.loads(incumbent_raw)
    _require(incumbent.get("status") == "accepted_complete_candidate_from_completed_normal_training_iteration"
             and incumbent.get("checkpoint_sha256") == INCUMBENT_CHECKPOINT_SHA256,
             "accepted incumbent receipt identity differs")
    golden_path = _absolute(incumbent["evaluation_jsonl_path"], "accepted incumbent JSONL path")
    _require(golden_path == INCUMBENT_GOLDEN_ROWS and incumbent.get("evaluation_jsonl_sha256") == INCUMBENT_GOLDEN_ROWS_SHA256
             and _file_sha(golden_path) == INCUMBENT_GOLDEN_ROWS_SHA256,
             "accepted incumbent golden rows differ")
    incumbent_checkpoint = _absolute(incumbent["checkpoint_path"], "incumbent checkpoint path")
    _require(incumbent_checkpoint.is_file() and _file_sha(incumbent_checkpoint) == INCUMBENT_CHECKPOINT_SHA256,
             "accepted incumbent checkpoint bytes differ")
    reference = reg["benchmark_reference"]
    _require(type(reference) is dict and set(reference) == {"certificate_path", "certificate_sha256"}
             and _absolute(reference["certificate_path"], "benchmark certificate path") == INCUMBENT_GOLDEN_ROWS
             and reference["certificate_sha256"] == INCUMBENT_GOLDEN_ROWS_SHA256,
             "benchmark reference must pin accepted 348 golden rows")
    cohorts = reg["cohorts"]
    _require(type(cohorts) is dict and set(cohorts) == {"benchmark_dev64", "ranking", "confirmation"},
             "cohort registration keys differ")
    chosen = cohorts[cohort_name]
    _require(type(chosen) is dict and set(chosen) == {"manifest_path", "manifest_sha256", "count"},
             "cohort manifest record fields differ")
    manifest_path = _absolute(chosen["manifest_path"], "manifest_path")
    manifest_raw = manifest_path.read_bytes()
    _require(_sha(manifest_raw) == chosen["manifest_sha256"], "cohort manifest byte SHA-256 differs")
    manifest = json.loads(manifest_raw)
    _require(type(manifest.get("seeds")) is list and type(chosen.get("count")) is int
             and chosen["count"] == len(manifest["seeds"]), "cohort count differs from manifest")
    seeds = manifest["seeds"]
    _validate_seed_vector(cohort_name, manifest, seeds)
    if cohort_name == "benchmark_dev64":
        _require(reg.get("mode") == "benchmark" and candidate_update == INCUMBENT_UPDATE,
                 "benchmark cohort must use only frozen dev-64 seeds")
        manifest_pin = _json(BENCHMARK_MANIFEST)
        _require(manifest_path == BENCHMARK_MANIFEST.resolve()
                 and chosen["manifest_sha256"] == BENCHMARK_MANIFEST_SHA256
                 and manifest.get("schema") == "expanded_D2_evaluation_seed_manifest_v1"
                 and manifest.get("cohort_name") == "benchmark_dev64"
                 and manifest.get("role") == "already_exposed_dev64_throughput_and_exact_replay_control_only"
                 and manifest.get("not_confirmation") is True and manifest_pin == manifest,
                 "benchmark manifest differs from parent integration pin")
    else:
        _require(reg.get("mode") == "ranking" if cohort_name == "ranking" else reg.get("mode") == "confirmation",
                 "registration mode differs from cohort")
        expected_role = "ranking" if cohort_name == "ranking" else "conditional_confirmation_only_if_winner_differs_from_accepted_348"
        _require(manifest.get("schema") == "expanded_D2_seed_manifest_proposal_v1"
                 and manifest.get("role") == expected_role and manifest.get("count") == len(seeds),
                 "expanded cohort manifest schema/role differs")
        if cohort_name == "ranking":
            pin = proposal["cohorts"]["ranking"]
            _require(manifest_path == Path(pin["path"]).resolve() and chosen["manifest_sha256"] == pin["sha256"]
                     and len(seeds) == 1024 and seeds[0] == 0xD1000000, "ranking manifest pin differs")
        else:
            pin = proposal["cohorts"]["confirmation"]
            _require(manifest_path == Path(pin["path"]).resolve() and chosen["manifest_sha256"] == pin["sha256"]
                     and len(seeds) == 2048 and seeds[0] == 0xD2000000, "confirmation manifest pin differs")
    if cohort_name == "confirmation":
        selection = reg["selection_record"]
        _require(type(selection) is dict and set(selection) == {"path", "sha256", "winner_update",
                 "winner_checkpoint_sha256", "incumbent_checkpoint_sha256"}, "confirmation selection record required")
        sel_path = _absolute(selection["path"], "selection record path")
        sel_raw = sel_path.read_bytes()
        _require(_sha(sel_raw) == selection["sha256"], "selection record bytes differ")
        sel = json.loads(sel_raw)
        _require(selection["winner_update"] in CANDIDATE_UPDATES and selection["winner_update"] != INCUMBENT_UPDATE
                 and sel.get("winner_update") == selection["winner_update"]
                 and sel.get("winner_checkpoint_sha256") == selection["winner_checkpoint_sha256"]
                 and selection["winner_checkpoint_sha256"] == reg["candidates"][str(selection["winner_update"])]["checkpoint_sha256"]
                 and selection["incumbent_checkpoint_sha256"] == INCUMBENT_CHECKPOINT_SHA256,
                 "confirmation is only valid for locked non-348 winner and 348 comparator")
        _require(candidate_update in (selection["winner_update"], INCUMBENT_UPDATE),
                 "confirmation candidate must be locked winner or 348 comparator")
    else:
        _require(reg["selection_record"] is None, "selection record is only valid for confirmation")
    output_dir = _absolute(reg["output_dir"], "output_dir")
    out = _absolute(output_path, "output_path")
    _require(out.parent == output_dir and not out.exists(), "output must be new path directly inside registered output_dir")
    _require(Path(reg["cancel_path"]).is_absolute() and Path(reg["one_shot_marker"]).is_absolute()
             and Path(reg["state_path"]).is_absolute(), "worker state paths must be absolute")
    _require(type(reg["limits"]) is dict and set(reg["limits"]) == {"outer_seconds", "work_seconds",
             "cleanup_seconds", "RSS_bytes", "MPS_driver_bytes", "guard_poll_seconds", "heartbeat_stale_seconds"},
             "registration limits fields differ")
    _require(type(reg["expected_lease"]) is dict and type(reg["review_records"]) is list
             and bool(reg["review_records"]),
             "parent lease/review records missing")
    for item in reg["review_records"]:
        _require(type(item) is dict and type(item.get("path")) is str and type(item.get("sha256")) is str,
                 "review record pin malformed")
        review_path = _absolute(item["path"], "review record path")
        _require(review_path.is_file() and _file_sha(review_path) == item["sha256"], "review record bytes differ")
    return reg, manifest, seeds, reg["candidates"][str(candidate_update)], output_dir, out


def _validate_rows(rows: list[dict], seeds: list[int], *, cap=18000) -> list[dict]:
    _require(type(rows) is list and type(seeds) is list and len(seeds) > 0 and len(seeds) % 4 == 0
             and len(rows) == len(seeds), "evaluation row count must be positive, divisible by four, and match manifest")
    _require([row.get("seed") for row in rows] == seeds, "rows missing, reordered, duplicated, or outside manifest")
    for index, row in enumerate(rows):
        _require(type(row) is dict, "row must be an object")
        for key in ("episode_index", "seed", "score_raw_fixed", "score_delta_sum_raw_fixed",
                    "alive_frames", "gameplay_frames", "startup_frames"):
            _require(type(row.get(key)) is int and row[key] >= 0, f"{key} must be a nonnegative integer")
        _require(row["episode_index"] == index and row["startup_frames"] == 13, "row identity/startup differs")
        _require(row["score_delta_sum_raw_fixed"] == row["score_raw_fixed"], "fixed score accumulation differs")
        _require(type(row.get("terminated")) is bool and type(row.get("truncated")) is bool
                 and row["terminated"] != row["truncated"], "episode boundary flags invalid")
        _require(row["alive_frames"] <= row["gameplay_frames"] <= cap, "raw frame bound exceeded")
        if row["terminated"]:
            _require(row["alive_frames"] + 1 == row["gameplay_frames"], "fatal-frame conservation differs")
            cause = row.get("death_cause")
            _require(cause in DEATH_CAUSES, "terminated row cause missing/invalid")
            if cause == "unavailable":
                _require(row.get("fatal_gameplay_frame") is None and row.get("death_observed_lethal_contacts") is None,
                         "unavailable telemetry cannot infer fatal contacts")
            else:
                contacts = row.get("death_observed_lethal_contacts")
                _require(row.get("fatal_gameplay_frame") == row["gameplay_frames"]
                         and type(contacts) is dict and set(contacts) == set(DEATH_CAUSES[:-1])
                         and all(type(v) is int and v >= 0 for v in contacts.values())
                         and (cause == "unknown" or contacts[cause] >= 1), "native death telemetry differs")
        else:
            _require(row["gameplay_frames"] == row["alive_frames"] == cap
                     and row.get("death_cause") is None and row.get("fatal_gameplay_frame") is None
                     and row.get("death_observed_lethal_contacts") is None, "truncation telemetry/frame cap differs")
        _require(type(row.get("score")) in (int, float) and math.isfinite(row["score"])
                 and row["score"] == row["score_raw_fixed"] / 65536, "score identity differs")
        expected = row["score_raw_fixed"] / 65536 + row["alive_frames"] / 100 - 5 * row["terminated"]
        _require(type(row.get("objective_return")) in (int, float) and math.isfinite(row["objective_return"])
                 and math.isclose(row["objective_return"], expected, rel_tol=0, abs_tol=1e-9),
                 "raw objective identity differs")
    return rows


def _summarize(rows: list[dict], seeds: list[int], started: float, checkpoint_sha: str,
               candidate_update: int, cohort_name: str, cohort_sha: str) -> dict:
    ordered = sorted(row["alive_frames"] for row in rows)
    q = len(rows) // 4
    performance = {"worst": ordered[0], "q1_bottom_quarter_mean": sum(ordered[:q]) / q,
                   "mean": sum(ordered) / len(ordered), "q4_top_quarter_mean": sum(ordered[-q:]) / q,
                   "best": ordered[-1]}
    deaths = [r for r in rows if r["terminated"]]
    return {"schema": "expanded_D2_candidate_evaluation_v1", "complete": True,
            "candidate_update": candidate_update, "checkpoint_sha256": checkpoint_sha,
            "cohort_name": cohort_name, "cohort_sha256": cohort_sha, "episodes": len(rows),
            "caps": sum(r["truncated"] for r in rows),
            "death_causes": {cause: sum(r.get("death_cause") == cause for r in deaths) for cause in DEATH_CAUSES},
            "performance": performance, "elapsed_seconds": time.monotonic() - started, "rows": rows,
            "evidence_limit": "ranking is selection-only; confirmation is one conditional winner-vs-348 comparison"}


def _verify_incumbent_golden_rows(rows: list[dict]) -> None:
    """The 348 benchmark is an exact replay check against its accepted 64-row certificate."""
    _require(_file_sha(INCUMBENT_GOLDEN_ROWS) == INCUMBENT_GOLDEN_ROWS_SHA256,
             "accepted 348 golden-row bytes differ")
    expected = [json.loads(line) for line in INCUMBENT_GOLDEN_ROWS.read_text().splitlines() if line]
    seeds = list(range(0xD0000000, 0xD0000040))
    _require(len(expected) == 64 and {row.get("seed") for row in expected} == set(seeds),
             "accepted 348 golden rows are incomplete or seed-misaligned")
    by_seed = {row["seed"]: row for row in expected}
    fields = ("seed", "episode_index", "alive_frames", "gameplay_frames", "score_raw_fixed", "score",
              "objective_return", "terminated", "truncated", "death_cause", "fatal_gameplay_frame",
              "death_observed_lethal_contacts")
    for row in rows:
        reference = by_seed[row["seed"]]
        _require(all(row.get(field) == reference.get(field) for field in fields),
                 f"candidate 348 benchmark row differs from accepted golden seed {row['seed']}")
    ordered = sorted(row["alive_frames"] for row in rows)
    _require((ordered[0], sum(ordered[:16]) / 16, sum(ordered) / 64,
              sum(ordered[-16:]) / 16, ordered[-1]) == (375, 867.0625, 3098.125, 6003.875, 8180),
             "candidate 348 benchmark performance differs from accepted certificate")


def _write_exclusive(path: Path, value: dict) -> str:
    encoded = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return _file_sha(path)


def _trusted_module_cache(root: Path) -> None:
    """Allow only exact cache from this pinned runtime, including sequential candidate reuse."""
    for name, module in tuple(sys.modules.items()):
        if name != "dodge_rl" and not name.startswith("dodge_rl."):
            continue
        origin = getattr(module, "__file__", None)
        _require(origin is not None, f"preloaded Dodge module has no origin: {name}")
        path = Path(origin).resolve()
        _require(path.is_relative_to(root) and path.is_file(), f"preloaded Dodge module origin rejected: {name}")
        relative = path.relative_to(root).as_posix()
        _require(relative in RUNTIME_MEMBERS and _file_sha(path) == RUNTIME_MEMBERS[relative],
                 f"preloaded Dodge module pin rejected: {name}")


def _production_rows(model, env_factory, observations_keys, death_fields, seeds, excluded_ranges, guard,
                     *, batch_size=64) -> list[dict]:
    import numpy as np
    import torch
    rows = []
    for offset in range(0, len(seeds), batch_size):
        chunk = seeds[offset:offset + batch_size]
        envs, obs, completed = [], [], {}
        for local, seed in enumerate(chunk):
            guard()
            env = env_factory(batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=True,
                powerups_enabled=True, raw_frame_cap=18000, num_threads=1, chunk_size=1,
                render_pixels=False, auxiliary_targets=False, seeds_by_slot=[[seed]],
                excluded_seed_ranges=excluded_ranges)
            info = env.episode_info()[0]
            _require(info["seed"]["evaluation"] is True and info["seed"]["actual_seed"] == seed
                     and info["startup_frames"] == 13 and info["gameplay_frames"] == 0,
                     "D2 constructor seed/startup differs")
            envs.append(env); obs.append(env.observations())
        while envs:
            guard()
            tensors = {name: torch.from_numpy(np.concatenate([obs[i][name] for i in range(len(envs))], axis=0))
                       .to(model._expanded_eval_device) for name in observations_keys}
            with torch.no_grad():
                output = model(*(tensors[name] for name in observations_keys))
            logits = output.logits
            _require(tuple(logits.shape) == (len(envs), 9) and bool(torch.isfinite(logits).all()),
                     "nonfinite or malformed D2 policy output")
            actions = logits.argmax(dim=-1).cpu().numpy()
            del tensors, output, logits
            for i in range(len(envs) - 1, -1, -1):
                guard()
                result = envs[i].step(np.array([actions[i]], dtype=np.int64)); info = result["info"][0]
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                _require(info["seed"]["actual_seed"] == chunk[i] and not (terminated and truncated)
                         and info["bootstrap"] == (not terminated), "D2 seed/boundary differs")
                _require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "fixed score identity differs")
                if terminated or truncated:
                    completed[i] = {"episode_index": offset + i, "seed": chunk[i],
                        "score_raw_fixed": info["score_raw_fixed"], "score": info["score_raw_fixed"] / 65536,
                        "alive_frames": info["alive_frames"], "gameplay_frames": info["gameplay_frames"],
                        "startup_frames": info["startup_frames"], "objective_return": info["objective_return"],
                        "score_delta_sum_raw_fixed": info["score_delta_sum_raw_fixed"],
                        "terminated": terminated, "truncated": truncated,
                        **death_fields(info, terminated, truncated)}
                    del envs[i], obs[i]
                else:
                    obs[i] = result["observations"]
            guard()
        rows.extend(completed[i] for i in range(len(chunk)))
    return rows


def evaluate_registered(*, registration_path: str, registration_sha256: str,
                        candidate_update: int, cohort_name: str, output_path: str,
                        check_guard: Callable[[], None]) -> dict:
    """Validate identity, load policy strictly on CPU, then evaluate ordered seeds in B=64 chunks."""
    global _BACKEND_IDENTITY
    _require(callable(check_guard), "check_guard must be callable")
    reg, manifest, seeds, candidate, output_dir, out = _validate_static(
        registration_path, registration_sha256, candidate_update, cohort_name, output_path)
    check_guard()
    runtime = reg["runtime"]
    _require(sys.implementation.cache_tag == "cpython-312", "Python interpreter differs from frozen native runtime")
    backend_identity = (runtime["backend"], runtime["torch_version"], runtime["numpy_version"],
                        runtime["pycache_prefix"], tuple(sorted(runtime["member_sha256"].items())))
    _require(_BACKEND_IDENTITY is None or _BACKEND_IDENTITY == backend_identity,
             "backend/runtime changed within sequential candidate worker")
    root = Path(runtime["root"]).resolve()
    _trusted_module_cache(root)
    # Backend and interpreter are externally pinned before the first runtime import.
    import numpy as np
    import torch
    _require(sys.pycache_prefix == runtime["pycache_prefix"], "Python cache prefix differs from registration")
    _require(torch.__version__ == runtime["torch_version"] and np.__version__ == runtime["numpy_version"],
             "Torch or NumPy version differs from registration")
    _BACKEND_IDENTITY = backend_identity
    _require(runtime["backend"] == "cpu" or torch.backends.mps.is_available(),
             "registered MPS backend is unavailable")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import dodge_rl
    from dodge_rl.models import OmniscientEntityTeacher
    from dodge_rl.dev_eval import death_fields
    from dodge_rl.identity import OBSERVATION_KEYS
    from dodge_rl.checkpoints import load_checkpoint
    import inspect
    from dodge_rl import dev_eval as dev_eval_module, identity as identity_module, checkpoints as checkpoints_module
    _require(Path(dodge_rl.__file__).resolve() == root / "dodge_rl/__init__.py", "Dodge package origin differs")
    for module, rel in ((dev_eval_module, "dodge_rl/dev_eval.py"), (identity_module, "dodge_rl/identity.py"),
                        (checkpoints_module, "dodge_rl/checkpoints.py")):
        _require(Path(module.__file__).resolve() == root / rel, f"Dodge module origin differs: {rel}")
    _require(Path(inspect.getfile(OmniscientEntityTeacher)).resolve() == root / "dodge_rl/models/teacher.py",
             "model source origin differs")
    native = Path(__import__("dodge_rl._native", fromlist=["__file__"]).__file__).resolve()
    _require(native == root / NATIVE_RELATIVE_PATH and _file_sha(native) == NATIVE_SHA256,
             "loaded native extension differs from registered pin")
    check_guard()
    checkpoint = Path(candidate["checkpoint_path"]).resolve()
    before = _file_sha(checkpoint)
    _require(before == candidate["checkpoint_sha256"], "checkpoint bytes differ before load")
    rng = torch.get_rng_state().clone()
    model = OmniscientEntityTeacher()
    torch.set_rng_state(rng)
    state = load_checkpoint(checkpoint, expected_sha256=candidate["checkpoint_sha256"])
    weights = state.get("model", state)
    model.load_state_dict(weights, strict=True)
    model.to("cpu")
    original_modes = [(module, module.training) for module in model.modules()]
    model.eval()
    model._expanded_eval_device = "mps" if runtime["backend"] == "mps" else "cpu"
    if runtime["backend"] == "mps":
        model.to("mps")
    model_sha_before = _model_state_sha(model.state_dict())
    _require(_file_sha(checkpoint) == before, "checkpoint bytes changed during load")
    started = time.monotonic()
    py_rng = __import__("random").getstate(); np_rng = np.random.get_state(); torch_rng = torch.get_rng_state().clone()
    grad_enabled = torch.is_grad_enabled()
    mps_rng = torch.mps.get_rng_state() if runtime["backend"] == "mps" else None
    try:
        excluded_ranges = json.loads(PROTOCOL_PATH.read_bytes())["training_excluded_ranges"]
        rows = _production_rows(model, dodge_rl.VecDodgeEnv, OBSERVATION_KEYS, death_fields,
                                seeds, excluded_ranges, check_guard, batch_size=64)
    finally:
        python_changed = __import__("random").getstate() != py_rng
        numpy_now = np.random.get_state()
        numpy_changed = not (numpy_now[0] == np_rng[0] and np.array_equal(numpy_now[1], np_rng[1])
                             and numpy_now[2:] == np_rng[2:])
        cpu_changed = not torch.equal(torch.get_rng_state(), torch_rng)
        mps_changed = runtime["backend"] == "mps" and not torch.equal(torch.mps.get_rng_state(), mps_rng)
        __import__("random").setstate(py_rng); np.random.set_state(np_rng); torch.set_rng_state(torch_rng)
        if runtime["backend"] == "mps":
            torch.mps.set_rng_state(mps_rng)
        for module, was_training in original_modes:
            module.training = was_training
        _require(not python_changed and not numpy_changed and not cpu_changed and not mps_changed,
                 "inference changed Python, NumPy, or Torch RNG; original states restored")
        _require(torch.is_grad_enabled() == grad_enabled, "global gradient mode changed during inference")
    rows = _validate_rows(rows, seeds)
    if cohort_name == "benchmark_dev64":
        _verify_incumbent_golden_rows(rows)
    _require(_model_state_sha(model.state_dict()) == model_sha_before, "policy weights changed during inference")
    _require(_file_sha(checkpoint) == before, "checkpoint bytes changed during inference")
    check_guard()
    result = _summarize(rows, seeds, started, candidate["checkpoint_sha256"], candidate_update,
                        cohort_name, _sha(Path(reg["cohorts"][cohort_name]["manifest_path"]).read_bytes()))
    result["elapsed_seconds"] = time.monotonic() - started
    result["registration_sha256"] = registration_sha256
    result["model_state_dict_sha256"] = model_sha_before
    result["backend"] = runtime["backend"]
    check_guard()
    written_sha = _write_exclusive(out, result)
    _require(_file_sha(out) == written_sha, "published output bytes changed")
    return result


def _model_state_sha(state: dict) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        digest.update(name.encode()); digest.update(b"\0")
        digest.update(str(tensor.dtype).encode()); digest.update(b"\0")
        digest.update(json.dumps(list(tensor.shape), separators=(",", ":")).encode()); digest.update(b"\0")
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()
