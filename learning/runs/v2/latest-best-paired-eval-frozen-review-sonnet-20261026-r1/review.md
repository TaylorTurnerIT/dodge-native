# Frozen review: latest-best paired eval (Sonnet fallback, readonly)

Target: `learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r1/` (receipt 0743556a…, protocol 8e30d4a7…).
Scope read: `worker.py`, `supervisor.py`, `paired_eval.py`, `input-manifest.json`, `protocol-proposed.json`, tests, frozen `dev_eval.py`, `crates/dodge-rl-env/src/python.rs`. No games, training, or `freeze_artifacts.py`.

**Verdict: do not launch. One blocking defect (F1) guarantees the one-shot campaign fails on its first live step.**

## F1 (blocking): `death_fields` runs on every live step
- `worker.py:302` calls `_canonical_row(...)` for every step, before the `if terminated or truncated` test at `:303`. `_canonical_row` unconditionally evaluates `**death_fields(info, terminated, truncated)` (`worker.py:245`).
- Frozen `dev_eval.death_fields` (runtime `dev_eval.py`) takes its `else` branch when `"death_cause"` is in `info` and the episode is not terminated. That branch does `require(truncated and cause is None ...)`. `python.rs:119-125` always sets `death_cause` (None when alive), so on a live step `truncated` is False and it raises `ValueError: Development death telemetry present on a non-terminated episode`.
- Frozen `dev_eval.evaluate` only calls `death_fields` inside `if terminated or truncated`. The port changed this.
- Impact: the first non-terminal step of the first arm (best180 argmax) raises. `run_worker` records `status: failed`, and the no-retry policy burns the whole campaign with zero usable rows. Every episode has live steps (13 startup frames, 18000-frame cap, action_repeat 4).
- Why tests missed it: `FakeEnv.step` (`tests/test_paired_eval.py:~49-58`) always returns `truncated=True` on the first call, so no live step is ever exercised.
- Fix: keep the boundary/seed/score/objective checks per step, but build the row and call `death_fields` only when `terminated or truncated`. Add a fake env that runs N live steps (info carrying `death_cause: None`) and then terminates and truncates, in separate tests. Both must pass through `evaluate`.
- Fixing this changes `worker.py`, so `harness_sha256`, the protocol, the manifest, and the lease hashes must be regenerated and the harness re-reviewed.

## F2 (medium): dependency bytes not pinned
- `input-manifest.json` pins 17 runtime files plus the interpreter, but no Torch, NumPy, or stdlib site-packages bytes. Both determine MPS logits, `torch.softmax`, the bootstrap RNG (`np.random.default_rng`, `np.quantile`), and so the control match and results.
- Minimal closure: add the exact version pins and file hashes already recorded in `D2-continuation180-parent-freeze-20261025-r4/registration-proposed.json`, verified in `verify_inputs`. No new watchdog.

## F3 (low, test gap): lifecycle untested
- Tests cover `terminal_status` only. `run_once` has no test with fake `popen`/`clock`/`sleep` for: work-deadline cancel, lease-cancel, resource-limit cancel, postflight failure, or publication failure. Add a small fake-`popen` test for the 590 s cancel and one for the postflight/publication-failure rewrite. Do not redesign the controller.

## Checked, no defect found
- Argmax controls: both run first and compare the full canonical rows (incl. death fields) to the saved dev rows. Mismatch aborts before any sampled arm (`worker.py:321-322`, `paired_eval.py:55-60`, `:63-71`).
- v3 authority: the receipt/audit/checkpoint SHAs, `schema`/`tag`/`eligibility`/counters binding, strict `load_state_dict`, and the no-grad assertions are consistent.
- Sampler: private SplitMix64 per (version, replicate, game seed); one draw per env step. It is independent of checkpoint and batch position. The CPU float64 inverse-CDF edge handling is correct.
- Statistics: 10000 draws, seed 764002, paired over 64 seeds; the C4 primary contrast; decision rules match the contract (equivalence needs the whole CI within ±100). Summaries serialize with `allow_nan=False` and 512 rows are order-checked.
- Lifecycle: the 590/600 s deadlines, 6 GiB RSS/MPS caps, group SIGTERM→SIGKILL with reap, and postflight/publication failure rewrite are logically sound. The worker's own 590 s clock starts later than the supervisor's, so the supervisor kill governs.

## Notes (not defects)
- The lease gate requires literal `haiku_review_status == "reviewed"` and `haiku_review_receipt_sha256` (`worker.py:339-343`). The parent must populate these with the Sonnet-fallback review hash, and the provenance should be recorded in the reconciliation.
- Per-step state reread (297993 B) and per-logit MPS→CPU copies are overhead risks. No budget failure is asserted without measurement; one measured dry timing (no games) would settle it.
