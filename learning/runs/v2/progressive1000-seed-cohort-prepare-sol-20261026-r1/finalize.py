"""Recheck recorded inputs and publish owned proposal receipt. Stdlib only."""
import hashlib
import json
from pathlib import Path
import sys

from seed_controls import (NAMED_RANGES, STUDY_ID, U32, canonical, digest,
                           normalize, training_seed)
from prepare import forbidden

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def load(name):
    return json.loads((HERE / name).read_bytes())


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")


def main():
    assert sys.dont_write_bytecode
    assert Path(sys.pycache_prefix) == HERE / "empty-pycache"
    assert list((HERE / "empty-pycache").iterdir()) == []
    manifest = load("input-manifest.json")
    extra = [
        "crates/dodge-rl-env/src/env.rs",
        "learning/runs/v2/expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/reconstruct.py",
        "learning/runs/v2/expanded-evaluation-seed-exposure-audit-luna-20261026-r1/report.md",
        "learning/runs/v2/expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/report.md",
    ]
    current = {x["path"]: x for x in manifest["inputs"]}
    for rel in extra:
        assert not forbidden(rel)
        data = (REPO / rel).read_bytes()
        current[rel] = {"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "purposes": ["final static source/provenance check"]}
    changes = []
    for row in current.values():
        assert not forbidden(row["path"])
        data = (REPO / row["path"]).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != row["sha256"]:
            changes.append({"path": row["path"], "recorded_sha256": row["sha256"], "current_sha256": sha})
    manifest["inputs"] = sorted(current.values(), key=lambda r: r["path"])
    save("input-manifest.json", manifest)
    save("input-recheck.json", {"checked_files": len(current), "changed": changes,
                               "scope": "recorded input files only; no claim about unrelated concurrent workspace changes"})
    parent_receipt = json.loads((REPO / "learning/runs/v2/expanded-seed-lineage-parent-validation-20261026-r5/receipt.json").read_bytes())
    lineage_manifest = json.loads((REPO / "learning/runs/v2/expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/manifest.json").read_bytes())
    assert parent_receipt["child_evidence_sha256"] == current["learning/runs/v2/expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/evidence.json"]["sha256"]
    assert parent_receipt["child_source_sha256"] == lineage_manifest["outputs"]["reconstruct.py"] == current[extra[1]]["sha256"]
    source = (REPO / "crates/dodge-rl-env/src/env.rs").read_text()
    constructor = source[source.index("pub fn new(config:"):source.index("pub fn batch_info")]
    assert constructor.index("normalize_seed_exclusions") < constructor.index("seed_for(") < constructor.index("Slot::unstarted")
    reset = source[source.index("fn reset_indices("):]
    assert reset.index("seed_for(") < reset.index("Slot::unstarted")
    vectors = load("seed-vectors.json")
    save("rng-reference-requirements.json", {
        "status": "unmeasured_parent_gate_not_a_reference",
        "study_id": STUDY_ID,
        "references_required": [{"replica": row["replica"], "complete_seed_vector": row["seeds"],
                                 "vector_sha256": row["vector_sha256"],
                                 "cpu_rng_state_sha256": None, "mps_rng_state_sha256": None}
                                for row in vectors["vectors"]],
        "accepted_parent_bindings": vectors["parent"],
        "required_bindings": ["study_id", "replica", "complete_six_field_vector", "canonical_vector_sha256",
                              "backend", "Python/NumPy/Torch versions and pinned runtime identity",
                              "accepted324 checkpoint and integrity receipt", "confirmation acceptance",
                              "fingerprint source hash", "independent probe provenance and parent acceptance"],
        "ordering": "Parent-authorized independent reference measurement and acceptance before actual restore/reseed; CPU global seed first, explicit MPS seed last, then both state digests under acceptedR5 contract",
        "reused_LR_study_states": False,
        "authority": "No actual probe, Torch/NumPy/native import, RNG read, restore or launch performed here"})
    refs = load("history-reconstruction.json")["reference_vectors"]
    union = normalize(list(NAMED_RANGES.values()))
    save("test-vectors.json", {"historical_log_reference_vectors": refs,
         "normalization_reference": {"input": [[9,12],[0,3],[4,8],[U32,U32]],
                                     "expected": [[0,12],list(NAMED_RANGES["B"]),[U32,U32]]},
         "forced_six_range_rejection": {"candidates": [x for pair in union for x in pair] + [42],
                                        "expected_counter": 12, "expected_actual_seed": 42},
         "bounded_overlap_control": {
             "future": training_seed(vectors["vectors"][0]["seeds"]["env_master_seed"],17,760,union),
             "conservative_historical_prefix": training_seed(4200000000,44,48),
             "historical_master": 4200000000, "real_observed": False,
             "interpretation": "Same actual u32 value in conservative prefix only; not proof of a consumed historical episode"}})
    log = (HERE / "tests.log").read_text()
    assert "Ran 17 tests" in log and log.rstrip().endswith("OK")
    save("test-results.json", {"exit_code": 0, "tests": 17, "status": "passed_synthetic_arithmetic_only",
         "command": "PYTHONPYCACHEPREFIX=<owned>/empty-pycache python3 -B <owned>/test_controls.py",
         "R5_compatibility": "Only canonical_vector_sha256 AST function compiled with stdlib hashlib/json; no probe worker or RNG code executed",
         "policy_minibatch_rng_reads": 0, "cache_empty": True})
    coverage = load("coverage-map.json")
    receipt = {
        "schema": "progressive1000_seed_cohort_preparation_receipt_v1",
        "status": "prepared_proposal_only_historical_freshness_blocked" if not changes else "prepared_partial_input_drift_blocked",
        "study_id": STUDY_ID, "owned_output": str(HERE),
        "coverage": {k: coverage[k] for k in ("real_observed_unique_seed_values", "original_logged_training_unique_seed_values",
                    "conservative_19_journal_envelope_unique_seed_values", "real_observed_cohort_collisions",
                    "conservative_envelope_cohort_collisions", "files_opened", "inventory_files")},
        "input_recheck": {"files": len(current), "changes": changes},
        "tests": {"passed": 17, "failed": 0, "initial_slot_controls": 192, "bounded_future_draws": 98304},
        "reference_status": "Three new-study independent measured CPU/MPS references required before actual restore; none generated here",
        "exclusion_status": "six-range canonical union proposed only; parent native installation and complete future reservations pending",
        "execution_scope": {"stdlib_read_hash_arithmetic_synthetic_only": True, "checkpoint_binary_reads": 0,
                            "checkpoint_deserializations": 0, "Torch_NumPy_native_MPS_calls": 0,
                            "policy_or_minibatch_RNG_reads": 0, "model_or_environment_constructions": 0,
                            "training_eval_actual_campaigns": 0, "qualification_outcome_or_run_seed_reads": 0,
                            "subdelegations": 0, "commits_or_pushes": 0, "writes_outside_owned_output": 0,
                            "registrations_reservations_leases_markers_written": 0, "owned_cache_empty": True},
        "authority": "None. Parent owns closure, reservations, registration, launch and acceptance. B/E qualification, D3 difficulty and student work remain closed.",
        "claim_limit": "Partial current JSON/JSONL snapshot plus pinned prior evidence; not global workspace freshness or entire-future-stream proof",
        "design_sha256": manifest["explicit_expected_pins"]["learning/runs/v2/progressive1000-curriculum-replica-parent-20261026-r3/experiment.json"],
        "cohort_file_sha256": hashlib.sha256((HERE / "cohort.json").read_bytes()).hexdigest(),
        "vectors_file_sha256": hashlib.sha256((HERE / "seed-vectors.json").read_bytes()).hexdigest(),
        "input_manifest_sha256": hashlib.sha256((HERE / "input-manifest.json").read_bytes()).hexdigest(),
    }
    save("receipt.json", receipt)
    save("output-manifest.json", {"files": [{"path": str(path.relative_to(HERE)), "bytes": path.stat().st_size,
                                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                          for path in sorted(HERE.rglob("*"))
                                          if path.is_file() and path.name != "output-manifest.json"]})
    print(json.dumps({"status": receipt["status"], "input_changes": changes, "tests_passed": 17,
                      "input_files_rechecked": len(current)}))


if __name__ == "__main__":
    main()
