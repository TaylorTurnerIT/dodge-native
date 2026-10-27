# Expanded Layer A runner preparation

Preparation only. No game, native module, Torch, checkpoint, MPS, lease, ledger, or campaign was touched. Parent interface: `expanded-eval-parent-integration-20261026-r1/interface-contract.json`.

## Files

- `worker.py`: loads only an externally supplied evaluator whose SHA-256 matches registration. Calls canonical `evaluate_registered(*, registration_path, registration_sha256, candidate_update, cohort_name, output_path, check_guard)`. One worker process handles two old-dev64 repeats, six serial ranking calls, or the gated winner/348 confirmation pair. Writes per-call partial/final results and a stage bundle; no ledger writes.
- `execute_once.py`: preflight callback runs before exclusive one-shot marker. Owns child process group, polls cancellation/lease/resource observer at 0.2s, enforces separate 6 GiB RSS and MPS limits, kills/reaps on stop, preserves outer receipt. Parent must provide callback that validates every registration input, seed cache, expected lease, cancellation state, and wall budget. Only parent owns lease and ledger state.
- `build_registration.py`: emits a visibly incomplete draft with canonical registration section names. Refuses absent/unreviewed sources and measured old-dev64 throughput. `validate_final` rejects absent lease/ledger, missing confirmation selection, and changed source pins. Never call it with a made-up source digest or fake review record.
- `test_runner.py`: CPU-only fake-process and fail-closed checks.

## Freeze and run order

1. Wait for sibling evaluator to freeze. Independently review it; then pin exact evaluator, worker, and launcher source hashes and external review records. Current evaluator path/hash and runtime member/backend/version pins are intentionally absent.
2. Parent reconciles lineage receipt SHA against proposal pin. Current file hash is `fe4b0cc6cbbc4b9ff4335c4462dbc120954f1bac0bac8c6c761d5c18636c0949`; builder checks it fail-closed.
3. Parent adds exact old-dev64 benchmark certificate and output location, accepted lease object, state/ledger path, cancellation path, runtime inventory and review records. Benchmark seed manifest is D0000000..D000003f; old D64 source harness is upper-D64, a distinct cohort. This draft does not claim old-dev64 timing or determinism.
4. Run benchmark twice on update 348, verify exact 64-row result and deterministic row/performance/identity equality. Use measured full-cap throughput with 2x projection and cleanup padding to fill registration work/outer caps. A frame bound is not a timing estimate.
5. Parent authorizes ranking mode only after benchmark pass. Worker runs original candidates 180/204/276/300/324/348 over exact 1024-seed manifest, sequentially, and sorts only after all six complete by mean descending then earlier update. No early best.
6. Confirmation requires parent-frozen selection record whose winner differs from 348 and pins winner/incumbent checkpoint digests. Worker evaluates that pair on exact 2048 confirmation seeds. One separate opening; no auto-accept or pointer update. Parent alone writes ledger and decides acceptance.

Registration remains nonlaunchable until all parent fields, input/cache checks, source/runtime pins, full benchmark measurement, independent review, and explicit mode authorization exist. Old incumbent reference is Worst/Q1/Mean/Q4/Best = `375, 867.0625, 3098.125, 6003.875, 8180`.

## CPU checks

`python3 -m unittest -v` passed 4 tests. These cover preflight-before-marker, fake process cancellation/kill/reap and partial receipt, absent review records, and changed source pin. Synthetic tests do not establish native/runtime validity, benchmark determinism, throughput, resource compliance, or qualification.
