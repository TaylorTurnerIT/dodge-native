# Frozen static review: D2 continuation prepare r3 (Haiku, r1)

Scope: read-only static review of the frozen target `learning/runs/v2/d2-continuation-prepare-luna-20261025-r3/`, checked against parent registration `learning/runs/v2/d2-continuation-parent-prepare-20261025-r1/registration-r1.json` (sha256 `bf425a502987b51b4e637cbe750eee652ce359baa07e229af84f291da3e931ed`). No training, rollout, evaluation, launch, lease, or source edits. Input hashes are in `receipt.json`.

## Verdict

No blocking findings.

## Coverage

- Read in full: `execute_once.py` (348 lines), `runner.py` (620 lines), `plan.json`, `README.md`, `registration-r1-pin.json`.
- Read partially: `test_outputs.py` (head and test names only).
- Test names listed only: `test_continuation_contract.py`, `test_launcher_lifecycle.py`.
- Not read: `test_torch_restore.py`, bodies of the contract and launcher tests, `implementation-result.json`, parent `parent-plan.json` and `preparation-receipt-r1.json` (hashed only).
- Greps: `elapsed_raw_frames` and `gameplay_frames` definitions in the frozen runtime `critic-diagnostic-parent-prepare-20261025-r1/runtime/dodge_rl/ppo.py:322-328`.
- Not run: no tests, no preflight rerun, no pin rehash. The parent reports those results; this review does not confirm them.

## Checked and consistent

- Continuation counters: `NEW_UPDATES=60`, `PHASE_START=72`, `PHASE_END=132`, `EXPECTED_TOTAL=180`; the loop uses `PHASE_START + update`. `continuation_cumulative_counters` adds parent cumulative to local counters.
- Output validator: `validate_outputs` checks the 60-row metrics journal, counters, `optimizer_steps` range, environment decisions `== local_update * 16384`, diagnostic identities, and development cohort seeds `0xD0000000..0xD000003F`.
- Frame conservation (`execute_once.py:189-191`): `ppo.py:327-328` defines `gameplay_frames` as the sum of `elapsed_raw_frames`, so the sum over completed episodes plus abandoned episodes equals `raw_frames` as counted by `runner.py:575`.
- Abandoned-episode records: `runner.py:499-501` writes parent records with kind `abandoned_parent_episode`, and `validate_episode_journal` (`runner.py:392`) excludes them. Fresh environment starts at the saved nonzero `next_episode_indices`, so no seed replay.
- Wall accounting: `PARENT_WALL_SECONDS=1188.34122675`; cumulative equals parent plus current iteration (`runner.py:528`, checked at `execute_once.py:70-75`).
- Parent acceptance: `validate_parent_terminal_receipt` (`runner.py:146-173`) binds schema, status, candidate SHA, registration SHA, wall, cumulative counter 120, and artifact manifest.
- Failure first-observed ordering: every `first_failure` and `signal_event` dict has `monotonic` (`runner.py:337`, `360`, `596`; `execute_once.py:224`, `308`), so `min(..., key=monotonic)` at `execute_once.py:310` does not KeyError.
- Worker status: a failure after `status="completed"` still leaves `first_failure` set, which `valid_worker_result` (`runner.py:375-380`) rejects.

## Findings (all low, none blocking)

1. **low** — `execute_once.py:203-212`. Comment says "No subprocess precedes the exclusive marker and full byte checks," but `launch-marker.json` is written at line 211 before `load_registration` (line 233). Registration is trusted for shape only (line 205-207) before the marker and `out.mkdir` (line 209-210). Consequence: an invalid registration still creates the output directory and marker, though no worker starts. Comment is inaccurate; behavior is fail-closed for launch.

2. **low** — `execute_once.py:278-333`. If a non-`Cancelled` exception escapes the `finally` block (e.g., an OSError from `save` or `read`), `return_code` is never assigned and no `publication-failure.json` is written. Python still exits nonzero, so acceptance is blocked. Receipt is incomplete in that case.

3. **low** — `execute_once.py:274-275`. `artifact-manifest.json` is written before `execution-result.json` and `publication-failure.json`, so the manifest does not cover the final receipts. Acceptance depends on the parent reading `execution-result.json` directly.

4. **low** — `runner.py:189-192`. Runtime identity excludes `*.pyc` (`path.suffix != ".pyc"`) and `__pycache__`. With `PYTHONPYCACHEPREFIX` set, `__pycache__` is never read. A sourceless `.pyc` placed directly in `dodge_rl/` would still be importable and not pinned. Requires a planted file in the isolated runtime; accidental drift is not a concrete path.

5. **low (budget assumption, unverified)** — `plan.json` `entry_and_final_evaluation_allowance_seconds=150`. Margin under the 1600 work cap is 85.33 s (`1600 - 1514.67`). The 150 s allowance covers worker startup, parent restore, two development evaluations (`runner.py:552`, `580`), and checkpoint saves. The reviewed artifacts do not record the measured evaluation or restore durations, so the allowance is an assertion. If the allowance is short, the run hits the work cap in finalization and is consumed without success.

## Disclosed limits (not reclassified as blockers)

- No internal aggregate-RSS observer; `Guard` samples only the worker's own `ru_maxrss` (`runner.py:350-357`). Aggregate launcher-plus-worker RSS and the 1800 s total must be enforced by the parent-owned external observer.
- No continuous MPS peak claim; `mps_driver_bytes` is sampled.
- Latest measured performance per `plan.json`: Q1 bottom 16 mean 533.3125, Q4 top 16 mean 2325.625, mean 1178.0625 alive frames over 64 D2 dev games. Score is outside the gate; competence (`mean_alive_frames >= 3060`) is independent of normal-training completion (`execute_once.py:192-193`).

## Not confirmed here

- Parent-reported test results (15 contract tests, 8 + 1 restore tests, full 13609-pin preflight in 1.22 s, actual accepted D2 model/Adam/CPU-MPS-RNG restore) are not rerun or verified by this review.
- Whether `Guard` samples cover every peak in `torch.mps.driver_allocated_memory` between samples.
- Runtime behavior of `collect_rollout`, `episode_resume_state`, and `evaluate` (outside frozen runner logic).
