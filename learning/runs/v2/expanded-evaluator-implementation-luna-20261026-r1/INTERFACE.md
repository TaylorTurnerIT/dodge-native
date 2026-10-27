# Expanded evaluator handoff

`expanded_eval.py` exports the sole production entry:

```python
evaluate_registered(*, registration_path: str, registration_sha256: str,
    candidate_update: int, cohort_name: str, output_path: str,
    check_guard: Callable[[], None]) -> dict
```

The evaluator follows `expanded_D2_evaluation_registration_v1` from the parent interface contract. Registration top-level sections are exact: `schema`, `run_id`, `mode`, `source`, `runtime`, `candidates`, `cohorts`, `selection_record`, `limits`, `output_dir`, `cancel_path`, `one_shot_marker`, `state_path`, `expected_lease`, `review_records`, and `benchmark_reference`.

`source` pins this evaluator plus worker and launcher paths and byte SHA-256 values. `runtime` pins the full 13-member map from the frozen D2 capsule, its native relative path, one backend (`cpu` or `mps`), Torch and NumPy versions, and Python `pycache_prefix`. A worker must use this same registration and runtime identity for its six sequential candidates.

`candidates` keys are string updates `180`, `204`, `276`, `300`, `324`, and `348`. Each value copies that candidate's checkpoint path/SHA and accepted source-receipt path/SHA from proposal r5. Candidate checkpoints and receipts are byte-checked before imports or constructors. No optimizer or RNG state is restored.

`cohorts` has exactly `benchmark_dev64`, `ranking`, and `confirmation`. Each item is `{manifest_path, manifest_sha256, count}`. Benchmark manifest must match the parent integration manifest and seeds must be ordered `0xD0000000..0xD000003F`. Benchmark mode accepts candidate 348 only and compares all 64 rows to its accepted golden JSONL. `benchmark_reference` pins that certificate path and SHA. Ranking and confirmation manifests must match proposal r5 exactly. Every cohort has positive `N % 4 == 0`, unique ordered unsigned seeds, and N episodes. New cohorts reject the protocol's excluded B/E and D128 ranges and require parent seed-lineage proof r5.

`selection_record` is `null` except in confirmation. Confirmation requires a byte-pinned selection record with a registered winner other than 348 and candidate 348 as comparator. It evaluates only that winner or 348. Ranking never opens confirmation.

The collector constructs at most 64 independent B=1 environments per chunk, uses deterministic argmax, no reset or filler episodes, and retains manifest order. It validates score conservation, objective identity, fatal-frame/death telemetry, cap, and all cause counts. Results use schema `expanded_D2_candidate_evaluation_v1`; `performance` order is `worst`, `q1_bottom_quarter_mean`, `mean`, `q4_top_quarter_mean`, `best`. Q1/Q4 sort each candidate's alive frames independently and average lowest/highest N/4.

The output path must be new and directly inside registered `output_dir`; publication uses exclusive creation. The evaluator never changes a pointer, lease, marker, or ledger. Parent owns ledger writes. Ranking is selection-only. Confirmation is one conditional winner-versus-348 comparison. Neither is qualification or stage-promotion evidence.

Tests use synthetic CPU policies/environments only. They establish code behavior, not native runtime qualification, backend determinism, performance budget, registration review, or launch authority.
