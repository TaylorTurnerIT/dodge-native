# Fixed-rollout lambda diagnostic R4 review

Target: `learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r4` (diagnostic.py `ee3b1ec1…a711b27`, controls_r4.py `bdea9980…638aa0`). Source-only static review. Nothing executed.

Verdict: no correctness defect in the analyzer recurrence, observed-return scan, or NPZ variant admission. Findings are test-coverage, validation asymmetry, and receipt gaps. None blocks.

## R3 closure

- R3 high (observed-return off-by-one): closed by reading. `diagnostic.py:175-176` updates `ret` before append. Hand arithmetic on the R3 reproduction data gives mean `-0.324192475`, matching `parent-validation-20261026-r3/reproduction.json` expected values.
- R3 medium (partial raw admitted with complete components): closed by reading. `diagnostic.py:51-52` (load_npz) and `:78-81` (analyze) require exact variant set. `controls_r4.py:112-121` covers 12 mixed subsets.
- R3 weak parity: partially closed. `controls_r4.py:34-48` checks per-element target and advantage against production `compute_gae` at atol 2e-7. Decomposition is still unasserted (F1).

## Findings

1. **medium, test-coverage**, `controls_r4.py:34-48`. No control asserts decomposition outputs (covariances, reconstruction, identity error, signed/norm change). A dropped cross-term in `diagnostic.py:113-128` still prints PASS. Fix: assert identity error near 0 and covariance entries by hand. Remove the duplicate recurrence at `diagnostic.py:113-129`; lines 128-129 are overwritten at line 130.
2. **low, test-coverage**, `controls_r4.py:81-91`. Observed-return values cover one slot and buckets `0` and `1_4` only. `5_16` and `17_plus` boundaries (4/5, 16/17) and multi-slot truncation/tail/reset are unvalued. Bounds read correct at `diagnostic.py:189-199`.
3. **low, validation**, `diagnostic.py:58-104`. `analyze` does not reject unexpected keys; `load_npz` does (`:53-54`). A typo key is accepted in memory but rejected from NPZ.
4. **low, test-coverage**, `diagnostic.py:83-87`. Raw bounds (elapsed outside `[1,4]`, negative score, non-integer raw dtype) unasserted.
5. **low, test-coverage**, `controls_r4.py:77-79`. Near-constant case uses zero values, so EV is exactly 0 by algebra; only `isfinite` is asserted.
6. **low, documentation**, `receipt.json`. `partial_other_variant_subsets_checked_per_path: 6`; code checks 12 per path (6 per direction). `npz_reader_rejections: 21` matches code.
7. **low, reproducibility**, `receipt.json`. Production `compute_gae` reference (`ppo.py` sha `b3cef91b…eeac5`, `controls_r4.py:14-17`) is not in receipt or manifest. Retained `controls.py` PASS rests on `controls-r3-legacy.log` with no R4 run log.

## Static limitations

- SHA-256 and reading only. No analyzer, controls, torch, runtime, or native execution.
- Hand arithmetic is not an execution result.
- Decomposition correctness is by reading only.
- No actual rollout, capture, checkpoint, environment, MPS, training, state, lease, or source write. Does not affect accepted best300 or its published playback.
