# D2-retained324 linear integrated r4 review (haiku, r1)

Scope: read-only review of `learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/` (runner, launcher, parent_adapter, registration_schema, build_registration, lr_schedule, tests, manifests, `registration-final-r2.json`, implementation.diff, logs, raw-exit). No tests, imports, subprocess, checkpoint loads, lease access, or training launched. Hashes below were computed by me.

## Verdict

**Not launch-ready. One blocker (lease state), plus limits.** Source-level prior findings are resolved.

## Digests (recomputed)

| file | sha256 | matches source-manifest |
|---|---|---|
| runner.py | e80fba02…19 | yes |
| execute_once.py | 6b27b570…28 | yes |
| lr_schedule.py | ef81e875…79 | yes |
| parent_adapter.py | 8091c8e9…8f | yes |
| registration_schema.py | ed21c10e…2f | yes |
| build_registration.py | 9e92a693…04 | yes |
| test_integrated.py | d680bed6…68 | yes |
| test_runner_schedule.py | 4117c9ff…55 | yes |
| registration-final-r2.json | 0a6bf982…cb | yes (equal to registration-draft-superseded.json) |

`registration-final.json` (ccfe078c…) is a superseded artifact; `registration-final-r2.json` is canonical.

## Blocker

**B1. Lease state does not match registered expected lease (preflight failure).**
- Path: `learning/runs/v2-orchestration/state.json`, key `active_long_campaign` = `null` (read 2026-10-26, this session).
- Registered `expected_lease` (`registration-final-r2.json`): `{authorization: user_continue_D2_training_v3, kind: D2_gradient_alignment, parent_checkpoint_sha256: c10d90ec…, run_id: D2-retained324-linear-lr-20261026-r1}`.
- Check: `runner.check_lease` (runner.py:240-242) requires exact equality. Called in `load_registration` (runner.py:517), in `Guard.check` every 0.15 s (runner.py:706-707), and in launcher poll loop (execute_once.py:368).
- Trigger: any launch now, including the preflight in `execute()` (execute_once.py:322).
- Consequence: launch fails before worker start. Not a source bug. Parent must set that exact lease dict in state before launch. The launcher must not edit or clear the lease (per its docstring). Verify this immediately before launch.

## Non-blocking limits / risks

**L1. Registered output path is not the review or registration directory.** `registration_schema.OUTPUT` and `registration["output"]` = `learning/runs/v2/D2-retained324-linear-lr-20261026-r1` (does not exist yet; launcher creates it, execute_once.py:325). Registration file itself is `registration-final-r2.json`, not `registration.json`. Any observer or auditor expecting `registration.json` must bind the actual path, not patch frozen files. Path: registration_schema.py:9; build_registration.py:178.

**L2. Stale message text, no behaviour effect.** Launcher execute_once.py:263 and runner.py:790 say "phase-300" but the selected candidate is phase 324 (retained300 directory name is historical). Source-manifest `run_id` field says `D2-retained324-linear-lr-20261026-r1` while directory is `...-integrated-luna-...-r4`. Cosmetic; do not patch frozen files for it.

**L3. Pre-launch evidence gap: `minibatch_count == 512` (runner.py:571).** Runtime `gradient_alignment.py:88` sets `minibatch_count = len(actions)`. Not verified here that the probe batch is 512 rows. If it is not, `validate_gradient_alignment` raises in the worker after the first PPO step, failing the run. Confirm with a CPU-only read of the probe construction, not a run.

**L4. Test side effect.** `test_integrated.test_builder_spec_manifest_pin_rewrite_and_collision_negatives` writes and deletes `registration-collision-test.json` inside the owned directory. Transient; not a source-integrity problem but violates a "no writes into owned dir during tests" reading.

**L5. Launcher validates gradient/finite/EV only per update inside worker; nonzero actor/critic gradient check is end-of-run only** (runner.py:989). Fail-closed; no schedule corruption path found.

## Prior findings: status

- Unpinned base → fixed: base registration digest and base manifest digest pinned (build_registration.py:21-22, 106-107); 13846 pin set and 13827 R1 overlap checked (lines 111-123).
- Wrong latest resource anchor → fixed: latest cost receipt `d3ddc427…` (latest anchor path matches `D2-retained324-parent-terminal-audit-20261026-r1`).
- Adapter/schema actual module wrong → fixed: origin checks at build_registration.py:104-105 and runner.py:479-481.
- Builder skipped schema → fixed: schema validated at build_registration.py:278 and main :297.
- Stale base critical keys → fixed by explicit overrides in `registration.update` (build_registration.py:169-260).
- Spec digest library-only → fixed: schema checks spec and helper digest (registration_schema.py:48-55); runner checks LR_SCHEDULE_SHA256 (runner.py:288-290, 477-478).
- Resource / PPO / source-schema gaps → fixed: limits (runner.py:264, registration_schema.py:56-62) and PPO dict (registration_schema.py:63-66).
- Launcher fixed-LR / no 60-row LR validation → fixed: `validate_metric_schedule` (execute_once.py:88-112) checks 60 rows, per-group LR, counters, spec digest.
- Pathcolocation / module-key mismatch → fixed: all registered code paths point to `OWN` (runner.py:283-287; registration `runner_path`, `launcher_path`, `parent_adapter_path`, `lr_schedule_path`).

## Schedule and checkpoint order (verified by reading)

- Order per update (runner.py:938-987): rollout → `stage_schedule_update` (sets optimizer LR, staged metadata) → `ppo_update` → finite_tree → progress check → gradient alignment → EV identity → `assert_effective_lr` → `commit_schedule_after_success` → counters update → metric row → evaluation at 336/348/360/372/384. Commit happens only after gates (lines 955-972).
- LR per update k: `lr_for_cum(372+k)`: k=1 → 3e-5, k=60 → 1e-5 (lr_schedule.py:43-50). Launcher and runner use same function.
- Checkpoint LR binding: 324 → 3e-5 (runner.py:189-191, saved with `expected = SCHEDULE_START_LR`); 336 → lr at cumulative 384; 384 → 1e-5. Matches test expectations.
- Counters: phase 324..384, cumulative 372..432, seed 4200000001 (registration_schema.py:13-14; runner.py:259-261, 278-279). Seed not in historical ranges (runner.py:279).

## Parent qualification (as stated by parent, with my check)

Parent reports evidence `D2-retained324-linear-integrated-parent-validation-20261026-r4/{test-receipt.json,real-parent-state-receipt.json,parent_state_gate.py}` and observer `D2-retained324-linear-execution-observer-parent-20261026-r1/` (observe.py sha f271b264…cc, not reviewed here). Evidence directories exist on disk. I did not reread their contents. I did not invoke `load_registration`, hardware, or lease. Parent-reported gate results are not independently verified in this review.

## Historical pins

- Base registration pin set: 13846 entries, checked by count at build_registration.py:111. Preservation evidence checked at 119-123 against manifest fields. Not recomputed here.
- `import_policy.pycache_prefix` = `…/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache`. Parent reports this is valid existing empty directory. Check at runner.py:245-252 requires absolute existing empty dir. Parent says it will verify before launch.

## Scope not covered

- No run of tests (I did not execute them per instructions).
- No validation of runtime `dodge_rl` semantics beyond names and signatures.
- Did not verify runtime `critic_diagnostics` field names beyond `gradient_alignment.py` lines shown.

## Required before launch

1. Set `state.json` `active_long_campaign` to exactly the registered `expected_lease` dict (parent-owned, not launcher).
2. Confirm probe batch size for `minibatch_count == 512` (L3).
3. Parent verify pycache prefix empty immediately before launch.
