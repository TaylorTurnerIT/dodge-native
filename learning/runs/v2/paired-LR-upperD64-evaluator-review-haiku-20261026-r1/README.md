# Independent source review: paired LR upper-D64 evaluator (r1)

Reviewed frozen target: `learning/runs/v2/paired-LR-upperD64-evaluator-luna-20261026-r1/`.
Scope: source, tests, logs, manifests, parent design. Read-only. No imports, tests, subprocesses, checkpoint loads, MPS, or evaluation.

Verdict: **not ready for an actual evaluation.** The helper is a sound preparation scaffold, but it does not enforce native conservation rules, does not bind checkpoint identity, and has no real collector adapter. No actual evaluation is authorized by this review.

## Integrity checks (passed)

- SHA-256 of `paired_eval.py` = `ab0b7d76…1efd0`, matching `artifact-manifest.json`.
- `test_paired_eval.py` = `c1b9c8cb…e8e72`, README = `c3db5992…adc`, `seed-manifest.json` = `e11e9d6a…c886c`. All match the manifest.
- Seed manifest equals the parent design's manifest (`e11e9d6a…c886c`).
- Seeds `0xD0000040..0xD000007F` = `3489660992..3489661055`, 64 unique, ascending. They sit inside the protocol's `training_excluded_ranges` entry `[3489660928, 3489661055]` (`docs/v2-m3-run-protocol.json:108`). The "training-excluded" label is therefore backed by the protocol, though the evaluator never asserts it in code.
- Constant pin `e25117bf…199b`, run ID `D2-retained324-continuation-20261026-r1`, endpoints 384/432: consistent between `paired_eval.py` (lines 18–23) and `design.json`.
- `cpu-tests-final.log`: 9 tests, OK. The earlier `cpu-tests.log` shows one ERROR (`collect_d2_rows` missing), so the final log postdates the fix. The final log has no command or interpreter header, so the run environment is not verifiable from the log alone.

## Blockers (fix before any actual evaluation)

### B1 — HIGH: null checkpoint pin passes for the linear arm
- Path: `paired_eval.py:118–125`, output at `:146`.
- Trigger: linear registration with `linear_endpoint.checkpoint_sha256` null (the design's own `linear_arm` value) and checkpoint metadata with `checkpoint_sha256: None`. `None == None` passes. `run_id` is checked the same way (`:124`), so two missing run IDs also pass.
- Consequence: linear arm runs with no checkpoint identity. The output records `checkpoint_sha256: null` and still reports success.
- Fix: require a 64-hex string SHA and a non-empty run ID. Require linear SHA and run ID to differ from the constant pins.

### B2 — HIGH: row validator does not enforce native frame conservation
- Path: `paired_eval.py:61` (bounds only), `:79–81`.
- Native contract:
  - Death frame is not counted alive (`crates/dodge-rl-env/src/env.rs:216–218`). So for terminated rows `alive_frames == gameplay_frames - 1`. Python test `python/tests/test_env.py:370` asserts this.
  - Cap truncation fires at `gameplay_frames >= raw_frame_cap` on a live frame (`env.rs:224`). With `action_repeat=4` and cap 18000 (divisible by 4), truncated rows must have `gameplay_frames == alive_frames == 18000`.
- Validator checks only `0 <= alive <= gameplay <= 18000`.
- Trigger: a collector returns a death row with `alive == gameplay`, or a truncated row with `gameplay == 1`. The synthetic fake env in `test_paired_eval.py:97–126` returns exactly that (`alive 1, gameplay 1, truncated True`), and `validate_rows` accepts it.
- Consequence: `mean_alive_frames`, Q1/Q4 and paired differences can be computed from physically impossible rows.
- Parity note: `python/dodge_rl/dev_eval.py:78–79` has the same gap. The new validator is no stronger than the frozen dev contract.
- Fix: terminated → `alive == gameplay - 1`; truncated → `gameplay == 18000 and alive == 18000`; live rows never occur in a completed set.

### B3 — HIGH: test fixtures encode the invalid shapes
- Path: `test_paired_eval.py:10–21` (`rows()`), used by all summary and validator tests.
- Died rows use `alive == gameplay`. Truncated rows use `gameplay = i*10` (0–630), not 18000.
- Consequence: the 9 passing tests certify a contract that disagrees with the native runtime. The green log is not evidence of native conformance.
- Fix: build fixtures from the native rules (B2) and add negative tests for each rule.

### B4 — HIGH: no real collector adapter; injected kwargs do not match
- Path: `paired_eval.py:140–142` calls `collector(seeds=…, difficulty=…, action_repeat=…, raw_frame_cap=…, batch_size=…, gradients=…, action_mode=…, reset_policy=…)`. `collect_d2_rows` (`:153–155`) accepts `model, env_factory, observation_keys, death_fields, check_guard, device` only. Passing it directly raises `TypeError`.
- The `seeds` and `reset_policy`/`action_mode`/`gradients` kwargs are advisory: `collect_d2_rows` ignores `seeds` and hardcodes the rest. Any adapter that drops them silently passes.
- Still missing: the wrapper that binds `model` (checkpoint-loaded, eval mode), `env_factory=VecDodgeEnv`, `observation_keys=OBSERVATION_KEYS` (`python/dodge_rl/identity.py:25`), and `death_fields` (equivalent to `python/dodge_rl/dev_eval.py:41–65`).
- Fix: write the adapter. It must reject any kwarg that differs from the frozen values and assert `seeds == SEEDS`.

### B5 — HIGH: checkpoint and collector identity are caller claims, not bindings
- Path: `validate_registration` `:110–127`, `evaluate_registered` `:129–151`.
- The helper compares caller-supplied `checkpoint_metadata` to registration and constant strings. It never hashes the checkpoint file bytes (reading bytes, not loading), never hashes the model `state_dict` after load, and never hashes collector source.
- Consequence: a wrong or different checkpoint with a matching claimed SHA is accepted and attributed to the pinned endpoint.
- Fix: the builder must compute the file SHA and state-dict hash itself, compare them to the pin, and record the collector source hash in output.
- The task asks for an outer wrapped actual-validation builder, not a helper that asserts metadata. Current code is the helper only.

### B6 — MEDIUM-HIGH: output is overwritten, not exclusively created
- Path: `paired_eval.py:150` `Path(output_path).write_text(...)`.
- Trigger: rerun with an existing output path. Consequence: prior result silently replaced; partial write on failure. Output is written after the whole collection, so a late failure loses all rows.
- Fix: open with `"x"` (exclusive), write to a temp file, and rename. Record the registration SHA and checkpoint SHA in output.

### B7 — MEDIUM-HIGH: `unavailable` death cause accepted for terminated rows
- Path: `paired_eval.py:68–71`, mirroring `python/dodge_rl/dev_eval.py:49–51`.
- Native runtime always emits death telemetry on death (`crates/dodge-rl-env/src/python.rs:116–127`; `env.rs:252` falls back to `Unknown`, never omits the field).
- Trigger: a collector or adapter whose info dict lacks `death_cause`. `death_fields` returns `unavailable`, validation passes, and `death_cause_counts["unavailable"] == 64` is reported as complete.
- Consequence: silent telemetry loss on the registered path.
- Fix: for the native path, fail closed on missing death telemetry. Allow `unavailable` only for an explicitly registered legacy path.

## Should fix (before the parent decides to run)

### S1 — MEDIUM: no RNG, weight, or grad-mutation checks
- Path: `collect_d2_rows` `:178–181` (`torch.no_grad` around forward only), `:207–208` (restore mode only).
- Missing: torch and numpy RNG state capture and comparison, parameter hash before/after, `p.grad is None` checks. Metadata does not record `gradients=False` as observed.
- Fix: capture and compare before/after; record in output.

### S2 — MEDIUM: paired summary lacks arm provenance
- Path: `paired_summary` `:96–108`. `linear_endpoint` is hardcoded (`:102`). No per-arm registration SHA, checkpoint SHA, or run ID appears in output.
- Fix: thread registration SHA, checkpoint SHA, and run ID from `evaluate_registered` output into the summary.

### S3 — MEDIUM: startup and score identity not auditable from rows
- Path: `collect_d2_rows:172–173` checks `startup_frames == 13` only at construction; `:193` checks `score_raw_fixed == score_delta_sum_raw_fixed` per step. Neither field is in the output row. `startup_frames` and `score_delta_sum_raw_fixed` should be recorded. Also `gameplay_frames == 0` at construction is not checked.
- Objective identity (`:194–196`) uses `score_raw_fixed`, while runtime (`env.rs:278`) uses `score_delta_sum_raw_fixed`. Equal under `:193`, so low severity, but the formula should match the runtime.

## Low

- **L1** `paired_eval.py:64` — `row["score"]` raises `KeyError`, not `ValidationError`. Non-dict rows raise `TypeError`. `evaluate_registered:135` JSON decode errors and non-dict registrations raise non-`ValidationError` exceptions. Rejection still happens before collector start, so the ordering requirement holds.
- **L2** `collect_d2_rows:167–170` omits `excluded_seed_ranges`, which `dev_eval.py:32` passes. Inert in evaluation mode (`crates/dodge-rl-env/src/seed.rs:125–137` does no exclusion check), but the config diverges silently. Add a test or comment.
- **L3** No seed-membership guard in the collector beyond the fixed `SEEDS` constant. The audit report (`paired-LR-eval-seed-audit-haiku-20261026-r1/report.md:30`) notes the only block is the Python dev guard, which this path bypasses. Acceptable only because `SEEDS` is constant.
- **L4** `validate_rows` checks no per-row relation between `score_raw_fixed` and contact counts. Not a native rule, so no action beyond B2.

## Requirement checklist

| Requirement | Status |
|---|---|
| Typed non-finite checks (score, logits) | Pass (`:64–65`, `collect:182`) |
| Bool and int type checks | Pass (`_integer`, `:62–63`) |
| Fatal contact checks | Pass for presence and cause≥1 (`:66–78`) |
| Fatal frame equals gameplay frame | Pass (`:74–75`) |
| Cap exactness and death `alive = gameplay−1` | **Fail** (B2) |
| Startup 13 identity | Constructor only (`collect:172`) |
| Score fixed identity | Per step only (`collect:193`), not in rows |
| Objective identity | Per step only (`collect:194–196`) |
| Seed order, duplicates, pool membership | Pass (`:55`, `:57`) |
| Endpoint checks | **Partial**; None bypass (B1) |
| Pairing labels | Pass (`:114`, `:145`) |
| Output exclusive creation | **Fail** (B6) |
| No-grad, model mode restore | Pass for no_grad forward; mode restored in `finally` (`:207–208`) |
| No RNG or weight mutation | **Not implemented** (S1) |
| Malformed input rejected before collector | Pass (ordering `:133–139`) |

## Deliverables not yet built

1. Production collector adapter: binds frozen `VecDodgeEnv`, `OBSERVATION_KEYS`, a `death_fields` equivalent to `dev_eval`, and checks injected kwargs.
2. Checkpoint binder: file-byte SHA against the pin, post-load state-dict hash, collector source hash in output.
3. Upgraded validator enforcing B2 conservation, startup/score/objective identity fields recorded in rows, and fail-closed death telemetry (B7).
4. Native-consistent test fixtures (replacing `rows()`) and negative tests for B1–B7 and S1.
5. Exclusive, atomic output with registration, checkpoint, and collector provenance (B6, S2).
6. Parent-owned: a real linear registration with non-null checkpoint SHA and run ID, a guard implementation, budget and runtime pins, and an explicit execution decision.
7. Parent-owned: acceptance of the seed label. The audit report says acceptance is required because prior nonuse is not proven and the scan was partial (`*.pt` and `*-sealed.log` files not inspected).

Not a sealed or independent set. Label stays: unselected, training-excluded, prior nonuse not proven.

## Limits

- Read-only review. Nothing was imported, run, or executed. Native behavior was inferred from Rust and Python source, not executed. Python test expectations were read from `python/tests/test_env.py:370`.
- Checkpoint binaries were not opened or hashed. Whether `checkpoint-000384-candidate.pt` exists and matches `e25117bf…199b` is unverified.
- Newer sibling `paired-LR-upperD64-evaluator-luna-20261026-r2/` exists and was not reviewed. This verdict covers r1 only.
- `cpu-tests-final.log` lacks command/interpreter header; I could not confirm the venv used.
- No registration, linear checkpoint receipt, guard, or budget exists yet. No actual evaluation is authorized here.
