"""Generate review pins only after focused tests pass; never executes episodes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
OWN = RUNTIME.parent


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: dict) -> None:
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def build() -> None:
    import torch
    from dodge_rl import checkpoints
    from worker import EXPECTED_INPUTS

    inputs = {relative: expected for relative, expected in EXPECTED_INPUTS.values()}
    context = {
        "learning/runs/v2/latest-best-paired-eval-parent-plan-20261026-r1/reconciliation.json":
            "ca9ec2ad5ca0aaf5ff899229256b08306f1e56072e6e2f221f106737c142bd0f",
        "learning/runs/v2/latest-best-paired-eval-design-haiku-20261026-r1/plan.json":
            "65104a03192f0f040551f8a86c7886dbffba526aa2f41ecbfc89cbfd76a55087",
        "learning/runs/v2/d2-continuation252-parent-terminal-audit-20261026-r1/canonical-performance-correction.json":
            "22ea28a115382abca1fa45a2023bd92132c6c0e7a99767db8a090663747e33a0",
        "learning/runs/v2-orchestration/postovernight-action-mode-r3-protocol.json":
            "90e3ae1cc8ba253e2e64a708f9b66ed59762e85668a15197d04d9265180ea741",
        "docs/implementation-plan-v2.md": sha(ROOT / "docs/implementation-plan-v2.md"),
        "docs/SPEC_PRIVILEGED_VIT_RL.md": sha(ROOT / "docs/SPEC_PRIVILEGED_VIT_RL.md"),
    }
    inputs.update(context)
    sources = {name: sha(HERE / name) for name in
               ("paired_eval.py", "worker.py", "supervisor.py", "tests/test_paired_eval.py")}
    harness_hash = digest(sources)
    runtime_files = {}
    for subtree in (RUNTIME, OWN / "docs"):
        for path in sorted(subtree.rglob("*")):
            if path.is_file():
                runtime_files[str(path.relative_to(ROOT))] = sha(path)
    runtime_hash = digest(runtime_files)
    lexical_python = ROOT / "python/.venv/bin/python"
    target_python = lexical_python.resolve()
    best_path = ROOT / EXPECTED_INPUTS["best180_checkpoint"][0]
    latest_path = ROOT / EXPECTED_INPUTS["latest252_checkpoint"][0]
    best = checkpoints.load_checkpoint(best_path, expected_sha256=EXPECTED_INPUTS["best180_checkpoint"][1])
    latest = checkpoints.load_checkpoint(latest_path, expected_sha256=EXPECTED_INPUTS["latest252_checkpoint"][1])
    architecture = best["identity"]["architecture"]
    if architecture != latest["identity"]["architecture"]:
        raise ValueError("Pinned checkpoint architectures differ")
    if best["schema"] != latest["schema"] or best["schema"] != "d2_training_v3_checkpoint_v1":
        raise ValueError("Pinned checkpoint schemas differ")

    protocol = {
        "schema": "latest_best_paired_eval_protocol_v1",
        "status": "frozen_proposed_pending_haiku_review_and_parent_reconciliation",
        "run_id": "latest-best-paired-eval-20261026-r1",
        "purpose": "Inference-only exploratory D2 paired evaluation of checkpoint-by-action-mode interaction.",
        "primary_question": "Does the latest-versus-best difference change under sampled versus argmax actions on the same current D development cohort?",
        "harness_sha256": harness_hash,
        "scope": {"inference_only": True, "gradients": False, "optimizer_instantiation": False,
                  "training": False, "checkpoint_writes": 0, "training_parent_selection": False,
                  "rollback": False, "D3": False, "student": False, "B_E_qualification": False,
                  "qualification_claim": False, "held_out_claim": False,
                  "new_seed_cohort": False, "training_exclusion_config_change": False},
        "cohort": {"source": "frozen dev_eval.development_seeds()", "count": 64,
                   "first_seed": 3489660928, "last_seed": 3489660991,
                   "seeds_sha256": digest(list(range(3489660928, 3489660992))),
                   "scope": "existing D development seeds, already excluded from training; diagnostic only"},
        "checkpoints": {
            "best180": {"path": str(best_path), "sha256": EXPECTED_INPUTS["best180_checkpoint"][1],
                        "receipt_path": str(ROOT / EXPECTED_INPUTS["best180_receipt"][0]),
                        "receipt_sha256": EXPECTED_INPUTS["best180_receipt"][1],
                        "audit_path": str(ROOT / EXPECTED_INPUTS["best180_audit"][0]),
                        "audit_sha256": EXPECTED_INPUTS["best180_audit"][1],
                        "development_jsonl": str(ROOT / EXPECTED_INPUTS["best180_development"][0]),
                        "development_sha256": EXPECTED_INPUTS["best180_development"][1],
                        "phase_update": 180,
                        "expected_argmax_alive_frames": {"bottom16_mean": 585.625,
                                                           "top16_mean": 3502.5625,
                                                           "mean64": 1854.46875}},
            "latest252": {"path": str(latest_path), "sha256": EXPECTED_INPUTS["latest252_checkpoint"][1],
                          "receipt_path": str(ROOT / EXPECTED_INPUTS["latest252_receipt"][0]),
                          "receipt_sha256": EXPECTED_INPUTS["latest252_receipt"][1],
                          "audit_path": str(ROOT / EXPECTED_INPUTS["latest252_audit"][0]),
                          "audit_sha256": EXPECTED_INPUTS["latest252_audit"][1],
                          "development_jsonl": str(ROOT / EXPECTED_INPUTS["latest252_development"][0]),
                          "development_sha256": EXPECTED_INPUTS["latest252_development"][1],
                          "phase_update": 252,
                          "expected_argmax_alive_frames": {"bottom16_mean": 532.8125,
                                                             "top16_mean": 3192.3125,
                                                             "mean64": 1604.078125}},
        },
        "runtime": {"root": str(RUNTIME), "tree_sha256": runtime_hash,
                    "native_extension": str(RUNTIME / "dodge_rl/_native.cpython-312-darwin.so"),
                    "native_extension_sha256": "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e",
                    "interpreter": {"lexical_venv_path": str(lexical_python),
                                    "symlink_target": os.readlink(lexical_python),
                                    "resolved_target": str(target_python),
                                    "target_sha256": sha(target_python)},
                    "helpers": ["development_environment_config", "development_seeds", "death_fields",
                                "OBSERVATION_KEYS", "checkpoints.load_checkpoint",
                                "checkpoints.require_complete_update", "OmniscientEntityTeacher",
                                "VecDodgeEnv"]},
        "architecture": architecture,
        "environment": {"stage": "D2", "difficulty": 2, "action_repeat": 4,
                        "patterns_enabled": True, "powerups_enabled": True,
                        "render_pixels": False, "raw_frame_cap_per_episode": 18000,
                        "layout": "64 independent B1 envs; batched policy over sorted shrinking active slots; no reset"},
        "schedule": {"episodes": 512, "argmax_first": ["best180", "latest252"],
                     "argmax_episodes_per_checkpoint": 64,
                     "sampled_replicates": [64001, 64002, 64003],
                     "sampled_episodes_per_checkpoint": 192,
                     "sampled_order": "replicate seed ascending, then best180, latest252; each arm uses sorted 64 D seeds",
                     "control": "Both argmax controls run first. Compare entire canonical rows, including death telemetry, to saved JSONL sorted by seed. First mismatch stops full campaign; no retry.",
                     "canonical_row_fields": ["episode_index", "seed", "score_raw_fixed", "score",
                                               "alive_frames", "gameplay_frames", "terminated", "truncated",
                                               "objective_return", "death_cause", "fatal_gameplay_frame",
                                               "death_observed_lethal_contacts"],
                     "censoring": "Keep all episodes. Report cap counts, denominators, right-censoring, and uncensored restricted summaries. Any cap marks primary campaign incomplete."},
        "sampler": {"version": "paired-eval-splitmix64-v1",
                    "key": "SHA256(ASCII(version|replicate_seed|actual_game_seed)); first 8 bytes big-endian state",
                    "stream": "increment modulo 2^64 by 0x9E3779B97F4A7C15; SplitMix64 finalizer; upper 53 bits divided by 2^53",
                    "key_excludes_checkpoint_and_active_batch_position": True,
                    "common_uniforms_across_checkpoints": True,
                    "probabilities": "float32 policy logits copied to CPU float64; stable torch.softmax float64; normalize by math.fsum float64 before CDF accumulation",
                    "zero_probability": "zero-width bins skipped",
                    "exact_boundary": "uniform equal to a cumulative edge selects the next positive bin",
                    "final_bin": "if accumulated CDF ends below 1, choose last positive-probability bin",
                    "historical_difference": "New registered CPU inverse-CDF sampler differs from historical MPS torch.distributions.Categorical; no global-generator or shrinking-batch RNG coupling."},
        "statistics": {"sampled_primary": "Mean 3 replicates within each seed, then sorted bottom/top 16 means and mean across 64 seed-level values.",
                       "replicates": "Report each replicate separately, including score/alive summaries and death counts/denominators; report median and max seed-level sample SD.",
                       "death_denominators": {"argmax": 64, "sampled": 192},
                       "contrasts": {"C1": "latest252_argmax - best180_argmax per seed",
                                     "C2": "best180_sampled_mean3 - best180_argmax per seed",
                                     "C3": "latest252_sampled_mean3 - latest252_argmax per seed",
                                     "C4_PRIMARY": "C3 - C2 per seed",
                                     "C5": "latest252_sampled_mean3 - best180_sampled_mean3 per seed"},
                       "bootstrap": {"unit": "64 paired game-seed clusters", "draws": 10000,
                                     "seed": 764002, "rng": "NumPy default_rng PCG64",
                                     "method": "One 10000x64 cluster-index matrix reused across all contrasts; percentile CI with linear interpolation."},
                       "decision": {"practically_similar": "Whole 95% CI within [-100,+100] alive frames.",
                                    "exploratory_clear_difference": "95% CI excludes 0 and absolute mean difference is at least 100 frames.",
                                    "otherwise": "Inconclusive; wide CI including zero does not disprove a theory."},
                       "scope": "Report all five contrasts; no qualification or multiple-comparison claim. CIs condition on fixed checkpoint pair and cohort, not training-replicate uncertainty."},
        "resources": {"work_seconds": 590, "cleanup_seconds": 10, "outer_wall_seconds": 600,
                      "aggregate_owned_rss_bytes": 6442450944, "mps_driver_bytes": 6442450944,
                      "sample_seconds": 0.25, "no_hashing_on_monitor_timer": True,
                      "no_concurrent_long_mps_training": True},
        "supervisor": {"single_owned_campaign": True, "launch_count": 1, "retry": False,
                       "future_output": str(HERE / "campaign-output"),
                       "child": "start_new_session; retain raw exit/cancellation/publication lineage; terminate exact owned process group; directly reap child and prove group absence; never signal after proven absence.",
                       "finalization": "Close stdout, stderr, episode, and resource streams before hashing and receipt publication; perform full preflight, postflight, and postpublication checks.",
                       "status_limit": "complete_pending_parent_acceptance is diagnostic only; parent acceptance remains required."},
        "lease_contract": {"parent_owned_only": True,
                           "state_path": str(ROOT / "learning/runs/v2-orchestration/state.json"),
                           "active_long_campaign": None,
                           "active_inference_diagnostic": {
                               "kind": "M3_latest_best_paired_eval",
                               "authorization": "inference_only_paired_diagnostic",
                               "run_id": "latest-best-paired-eval-20261026-r1",
                               "protocol_sha256": "exact protocol file hash",
                               "harness_sha256": harness_hash,
                               "input_manifest_sha256": "exact input-manifest.json hash",
                               "campaign_launch_authorized": True,
                               "haiku_review_status": "reviewed",
                               "haiku_review_receipt_sha256": "64 lowercase hex chars",
                               "parent_reconciliation_sha256": "64 lowercase hex chars",
                               "no_concurrent_long_mps_training": True,
                               "cancel_requested": False},
                           "required_review_fields": ["haiku_review_receipt_sha256",
                                                       "parent_reconciliation_sha256"],
                           "lease_lifecycle": "Parent installs/clears lease; worker never writes state.json or lease."},
        "input_files_sha256": {str(ROOT / name): value for name, value in inputs.items()},
        "launch_state": {"campaign_launched": False, "game_episodes_executed": False,
                         "training_executed": False, "frozen_haiku_review_required": True,
                         "parent_reconciliation_required": True},
    }
    protocol_path = HERE / "protocol-proposed.json"
    write_json(protocol_path, protocol)
    manifest = {
        "schema": "latest_best_paired_eval_input_manifest_v1",
        "status": "frozen_source_and_input_manifest_for_review",
        "protocol_path": str(protocol_path), "protocol_sha256": sha(protocol_path),
        "harness_source_files": sources, "harness_sha256": harness_hash,
        "support_files": {"README.md": sha(HERE / "README.md"),
                          "freeze_artifacts.py": sha(HERE / "freeze_artifacts.py")},
        "input_files": inputs,
        "absolute_input_paths_sha256": {str(ROOT / name): value for name, value in inputs.items()},
        "frozen_runtime_root": str(RUNTIME), "frozen_runtime_files": runtime_files,
        "runtime_tree_sha256": runtime_hash,
        "interpreter": {"lexical_venv_path": "python/.venv/bin/python",
                        "symlink_target": os.readlink(lexical_python),
                        "resolved_target": str(target_python), "target_sha256": sha(target_python)},
        "native_extension_sha256": "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e",
        "architecture": architecture,
        "checkpoint_loader": "Frozen dodge_rl.checkpoints.load_checkpoint plus require_complete_update; strict d2_training_v3_checkpoint_v1, complete-update, identity, registration/runtime/native/policy/counter and accepted receipt/audit bindings.",
        "immutability": "No source/runtime/checkpoint/receipt/ledger/docs/lease outside this new preparation directory was modified.",
    }
    write_json(HERE / "input-manifest.json", manifest)
    print(json.dumps({"protocol_sha256": manifest["protocol_sha256"],
                      "harness_sha256": harness_hash, "runtime_tree_sha256": runtime_hash,
                      "input_manifest_sha256": sha(HERE / "input-manifest.json"),
                      "input_file_count": len(inputs), "runtime_file_count": len(runtime_files),
                      "parameter_count": architecture["parameter_count"]}, sort_keys=True))


if __name__ == "__main__":
    build()
