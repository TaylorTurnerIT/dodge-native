# D2 retained204 lr1e-4 r2 frozen review

Verdict: not ready for lease or launch. One blocker (B1): the launcher's output validator raises at evaluation update 204, after the one-shot training run has already consumed up to 1790 s. Retries are 0.

Target: `learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r2/`, registration `ef53c4aaf9e71b1ff93c1e03aa7871b829044b85a510d3f39a13e0380eaf623f`, source manifest `64bb691a1314081cf0d7834f3a223c0f8e0ff8f8937b7030fb10e8d26e4b3916`.

Scope: static read-only review plus pure-validator replays on registered artifacts. No lease, preflight, worker, launcher, MPS, environment, training, or checkpoint decode. This review grants no launch authority.

## Blocker

**B1. Output validator raises `StopIteration` at update 204.** `execute_once.py:168` is `expected_counters = row = next(item["counters"] for item in metrics if item["phase_update"] == update)`. `metrics` holds only phase updates 205–276 (`execute_once.py:85`). The evaluation loop starts at 204 (`execute_once.py:136`, `runner.py:43`). Reproduced in memory: the generator raises `StopIteration` for 204. `execute()` catches it (`execute_once.py:320`), sets status failed, and the run is rejected after training. This embedded-checkpoint block (`execute_once.py:165-185`) is new in r2. The parent's executed validator (`D2-best180-branch-prepare-luna-20261026-r1/execute_once.py`) had no such block. `test_source_contract.py` checks only source text, so nothing ran this path.

Fix: for `update == r.PHASE_START`, expect zero counters `{"updates":0,"optimizer_steps":0,"environment_decisions":0,"raw_frames":0}`; drop the `row =` chaining. Add a non-MPS fixture test that runs `validate_outputs` over synthetic 204–276 artifacts. Any source edit changes pins and the manifest, so re-freeze and re-review the new hashes before the parent proceeds.

## Prior findings: closed by code inspection

- Helper import before pin verification (prior review F1; r1 F1): helper origin is asserted at `runner.py:146-149`, the helper is in the critical set (`:371-375`) and digest-bound (`:375-377`), and it is executed only from hashed bytes after `verify_pins` (`:349-362`, `:369`). No `resume_lr_transition` import remains (grep).
- Digest timing, non-LR fields, saved LR (prior F2; r1 F2): the pre-override record is taken at `runner.py:731-735` before `apply_resume_lr_override` (`:740`). `resume_lr_transition.py:173-204` hashes immutably and computes `non_lr_fields_changed`. Saved LR is asserted at `runner.py:809` and `execute_once.py:185`. CPU negative controls passed (`cpu-restore-and-controls.json`).
- Archival config label (prior F3): registration validates `archival_parent_checkpoint_sha256` (`runner.py:122-123`). Config bytes are unchanged (see S1).

## Open, non-blocking (carry to parent)

- F4 (r1): entry rows are compared with accepted phase-204 rows only after all 72 updates (`execute_once.py:186-190`). Move the check to immediately after `runner.py:813`. Precedent: the parent passed the same check at 180 (parent `execute_once.py:164-167`; `execution-result.json` status passed).
- F5 (r1): `runner.py:864` sets status `completed` before the finalization guard (`:874`); the except block (`:875-878`) does not reset it. `valid_worker_result` still rejects on the `error` key (`:626-631`). Set status `failed` in the except.
- F6 (r1): comment at `execute_once.py:245-246` says no subprocess precedes the marker and full byte checks. The marker is written at `:253`, before `load_registration` at `:275`, and the registration is read unverified at `:247`. Fix the comment or move the marker.
- F7 (r1): `execute_once.py:353` writes `execution-result.json` with exclusive open. A cancel mid-write leaves a partial file, while the comment at `:361-362` says the primary receipt remains untouched.
- F8 (r1): `execute_once.py:193` reuses `certificate` from the last loop iteration. Read `development-000276.json` explicitly.

## Scope notes

- S1: config `D2-retained204-lr1e4-config.json` carries archival `parent_checkpoint_sha256` `ce9c03c8…`. Its sha matches `milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt`. Its `phase_settings.run_seed` `5562881586070242562` is inert: the registration `run_seed` `3791628418` governs (`runner.py:140`, `:754-759`), but the identity hash embeds the whole config. Labels only; authority fields are correct.
- S2: launcher wait loop (`execute_once.py:293-300`) checks lease, total deadline, and signals, but not `cancel_path`. Only the worker honors cancel and the work cap (`runner.py:597`). A native hang runs to 1800 s; cleanup (TERM and KILL, 5 s each) can push past the outer cap by up to about 10 s. Not reached at the expected ~1319 s.
- S3: post-worker validation and postflight (`execute_once.py:309`, `:313`) fall outside the worker's 1790 s work cap. Only `elapsed < 1800` is checked (`:310`, `:315`, `:318`). Checkpoints are about 3.9 MB, so likely seconds, but not budgeted.
- S4: MPS RNG restore uses `restore_learner` → `restore_rng` MPS branch (`checkpoints.py:138-142`, `:40-42`). The parent worker ran this path with entry-restoration matching model, Adam, and RNG (parent `entry-restoration.json`). Not re-run here.
- S5: entry-row reproduction on MPS for 204 has no 204-specific run. Parent precedent at 180 only.
- S6: frame conservation holds by construction: gameplay advances by elapsed (`ppo.py:327-328`), resets start at 0 (`:354`), counters add elapsed (`runner.py:854`). Not checked on a real 204 journal.
- S7: `test_source_contract.py` checks text and order only. It does not execute the validator or worker, which is why B1 passed.
- S8: lease not installed. `v2-orchestration/state.json` `active_long_campaign` is `None`. Output dir and `cancel-requested` are absent.
- S9: full 13767-pin verification (about 658 MB) was not run here. Parent gate.

## Replayed on actual artifacts (read-only)

- Hashes match registration, manifest, and preparation receipt.
- `validate_registration`, `validate_parent_terminal_receipt` (candidate receipt `7fd26ae3…`, audit, selection, evaluation, whole-iteration receipt), `validate_capsule_support`, `validate_runtime_continuity`, `validate_config_transition` (only `ppo.learning_rate` 0.0003→0.0001), and `validate_arm_binding` all pass.
- Parent phase-204 development file: seed set, performance summary, objective identity, death and cap counts, termination flags, and competence predicate all pass the validator's logic.
- Parent 72 training-metric rows: per-update counts, counters, progress, critic moments, and `validate_gradient_alignment` give 0 failures. Total optimizer steps 8224 match the registered control.
- Wall constants: `1177.4321468750002 × 9216 / 8224 = 1319.457 s` ≤ 1600 preregistered. Trajectory 3352.046 s and completed-campaign cost 4129.757 s are distinct fields.

## r1 reconciliation

The r1 reviewer's final receipt (`D2-retained204-lr1e4-review-haiku-20261026-r1/receipt.json`, sha `7fa65822…`) gives `not_ready_for_lease_until_pre_lease_fixes`, blockers F1 and F2, and reviewed r1 bytes (runner `5163633a…`). r2 closes F1 and F2 in code. r1's F4–F8 and scope notes F3 and F9–F12 still apply, as listed above. r1's F13 (r2 unreviewed) is resolved by this review. The r1 review did not cover the r2-only embedded-checkpoint block, so B1 is new.

## Not run

No preflight, lease, MPS, worker, launcher, environment, training, checkpoint decode, or full pin verification.

## Next

Parent fixes B1 (and optionally F4, F5), re-freezes, and gets this review re-run on the new hashes. Then the parent runs full pin, interpreter, and no-bytecode gates, installs the exact lease, and launches once.
