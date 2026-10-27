# Retained324 linear auditor source review (r1)

Reviewed: `learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r1/` (immutable), against predecessor source `learning/runs/v2/D2-retained324-all-candidate-auditor-luna-20261026-r2/` (`audit_candidates.py` sha256 `1addab84...`, `wrapper.py` `a915a4a0...`, `full-audit.json` `a897963f...`).

Not read: treatment `D2-retained324-linear-integrated-luna-20261026-r4` (path strings only, as in the binding builder). No code, tests, imports, checkpoints, MPS, lease, or state touched. No run dir exists (`D2-retained324-linear-lr-20261026-r1` absent). No `audit-binding.json` exists. `empty-pycache/` is empty.

## Verdict

No blocker to the CPU-synthetic evidence itself. Schedule math, six-candidate loop, 60-row progression, and the unchanged checks (state identity, resume, certificates, terminal gates, cache, source pins) read consistently with the spec.

Two HIGH gaps block parent freeze of the binding. The binding gate does not meet the stated requirement that dynamic bindings be immutable and hash-checked. Fix both before the parent writes `audit-binding.json`.

## Findings

Severity: HIGH blocks binding freeze. MEDIUM fix before acceptance. LOW note.

### 1. HIGH — binding file is trust root but has no hash pin or record

- Path: `audit_candidates.py:146`, `wrapper.py:74`, outputs at `audit_candidates.py:632-646` and `wrapper.py:293-310`.
- Trigger: `audit-binding.json` is rewritten or recreated (it is in writable `OUT`; builder's `open("x")` only stops overwrite, not delete-then-rebuild). New binding carries a different registration SHA, observer path/SHA, reviewed-manifest SHA, or auditor-source SHAs.
- Consequence: `load_frozen` computes `binding_sha` at line 146 but never compares or uses it. Neither the full-audit JSON nor the wrapper record includes the binding SHA. The whole chain (registration → runner/launcher/receipts, observer, auditor sources) hangs on an unhashed file, and a later full audit cannot show which binding it used.
- Fix: parent supplies the expected `audit-binding.json` SHA explicitly (or it is pinned in `frozen-manifest`) and the wrapper/auditor record `binding_sha256`. Keep the path check on `OUT / "audit-binding.json"`.

### 2. HIGH — binding builder self-computes auditor-source pins

- Path: `binding_builder.py:45` (`source_pins = {... sha256(HERE / name) ...}`), `binding_builder.py:52`.
- Trigger: any of `audit_candidates.py`, `wrapper.py`, `binding_builder.py`, `schedule_contract.py`, `lr_schedule.py` edited after review and before builder run.
- Consequence: builder records whatever bytes exist at build time. Unlike registration, observer, and reviewed manifest, these are not supplied as explicit SHA-256. Auditor and wrapper then accept the edited source. `frozen-manifest.json` already lists the reviewed SHAs for all five, but the builder never compares against them.
- Fix: require explicit `--<name>-sha256` for each source (or compare to `frozen-manifest.json` `files` values) and fail on mismatch, as is already done for the three external inputs.

### 3. MEDIUM — schedule modules imported by unpinned sys.path lookup

- Path: `audit_candidates.py:21` (`import schedule_contract`, module top level), `schedule_contract.py:7` (`import lr_schedule`).
- Trigger: a `schedule_contract.py` or `lr_schedule.py` earlier on `sys.path` than `OUT`, or a `.pyc` written by a run without `-B`. Import runs before `bind_environment()` (line 125) and before any SHA check (`load_frozen`, line 137+).
- Consequence: the validators that carry all schedule authority may not be the bytes whose SHAs are in the binding. The check `sha_file(path_text) == digest` (line 154-156) reads disk, not the loaded module. This violates the requirement that module origins be exact and not unpinned inputs. Predecessor used `load_pinned_module` for all frozen code.
- Narrow trigger: wrapper flow checks `PYTHONPATH` (`wrapper.py:117`) and `-B` before `load_auditor` (line 269), and the documented cwd is `OUT`.
- Fix: load `schedule_contract` and `lr_schedule` through `load_pinned_module` with binding SHAs, or assert `schedule_contract.__file__` and `schedule_contract.lr_schedule.__file__` equal the pinned `OUT` paths and their SHAs.

### 4. MEDIUM — independent constants overwritten by registration values

- Path: constants `audit_candidates.py:41-47` (`CONFIG_SHA`, `PARENT_SHA`, `PARENT_RECEIPT_SHA`, `NEW_NATIVE_SHA`, `LAUNCHER_SHA`, `REG_SHA`), overwritten at `audit_candidates.py:184-189`.
- Trigger: a final registration bound by a valid binding SHA but naming a different parent checkpoint, terminal receipt, native, or config.
- Consequence: the `Critical pin differs` check (line 206-208) now compares the registration to itself. The predecessor's hard-coded `c10d90ec...` (parent), `76cb1573...` (selected receipt), `022d41dd...` (native), and `1c24df...` (config) no longer gate anything. Parent substitution is caught only indirectly (entry rows vs `PARENT_EVAL_JSON_SHA`, entry model/Adam/RNG vs parent).
- Fix: keep the constants and assert `registration value == constant` for each. Do not replace them with registration values.

### 5. MEDIUM — observer instantiation hash pin removed

- Path: `audit_candidates.py:583-586`. Predecessor pinned `instantiation.json` to `4ce6cb20...` (diff line removed).
- Trigger: `OBSERVER_DIR/instantiation.json` replaced with a record whose `schema`, `observer_sha256`, `registration_sha256`, `run_id`, `actual_launches`, `one_shot_marker_absent` match.
- Consequence: file identity now rests on field checks only (`validate_observer_instantiation`, line 435-442). The file is parent-owned and its SHA is recorded in `tracked` but never pinned in the binding.
- Carry-over: `observation.json` (`audit_candidates.py:660`, `wrapper.py:282`) is also unpinned, same as predecessor.
- Fix: put `instantiation.json` and `observation.json` expected SHAs in the binding or the parent's acceptance record; verify before use.

### 6. LOW — terminal JSON read twice, not bound to audited bytes

- Path: `wrapper.py:280-282` re-reads `execution-result.json`, `worker-result.json`, `observation.json` with plain `read_bytes`. `audit_candidates.py:654-660` reads the same files with `stable_json` and discards the SHA.
- Trigger: file changed between the auditor read and the wrapper read.
- Consequence: `terminal_gates` may validate different bytes than the auditor did. Parent-written files post-reap make this unlikely, but the bytes are not tied.
- Fix: return the audited bytes/SHA from `audit()` and have the wrapper gate on those.

### 7. LOW — `load_frozen` accepts relative observer path

- Path: `audit_candidates.py:159-161`. `OBSERVER_SOURCE = Path(binding["observer_source"]["path"])` with no absolute check. The builder checks `is_absolute` (`binding_builder.py` `checked_bytes`), the loader does not.
- Trigger: hand-edited binding with relative path.
- Consequence: resolves against CWD.
- Fix: apply `is_absolute` check at load.

### 8. LOW — `verify_frozen_manifest` cannot read the new frozen manifest

- Path: `lr_schedule.py:117-123` expects a two-key dict (`schedule_spec_sha256`, `schedule_source_sha256`). `frozen-manifest.json` in the prep dir has a different schema (`schema`, `files`, `cpu_controls`, `limits`, ...).
- Trigger: any caller of `verify_frozen_manifest(OUT)`. None found in the reviewed files, so it is dead or a trap.
- Fix: remove, or align to the `files` map used by the prep manifest.

### 9. LOW — helper mutates LR before caller commits; horizon not bounded

- Path: `lr_schedule.py:111` sets `group["lr"]` inside `apply_next_update_lr`, before the docstring's "commit only after PPO update succeeds" (line 113 stages metadata). `validate_schedule_state` (`lr_schedule.py:84`) does not bound `completed_schedule_updates <= 60`; `learning_rate_for_cumulative_update` holds `END_LR` silently past horizon.
- Trigger: PPO update fails after LR is set and a checkpoint is written before retry; or runner keeps stepping past 60.
- Consequence: checkpoint LR and metadata disagree (auditor fails closed at `schedule_contract.py` `_check_state`), or beyond-horizon steps go unnoticed until the audit (auditor checks `local <= 60`, so it does fail closed).
- Fix: bound completed to `[0, HORIZON]` in `validate_schedule_state`; stage LR and commit only after success, or document the retry invariant.

### 10. LOW — `check_saved_lr` misses non-dict counters

- Path: `audit_candidates.py:282-283`. `state.get("inherited_counters", {}).get("updates")` raises `AttributeError` if the value is not a dict (not caught by `except (KeyError, TypeError, ValueError)`, line 288).
- Consequence: unhandled exception instead of `AuditError`. Still fails closed.
- Fix: check `isinstance` before `.get`.

### 11. LOW — full-mode guard is convention, not enforced

- Path: `audit_candidates.py:563` (`audit(provisional=False, observer_dir=...)` callable by any importer), `wrapper.py:318` (`full_mode`). CLI refusals at `audit_candidates.py:706-707` and `wrapper.py:328-329` only cover the command line.
- Consequence: full mode requires binding + observer dir, so impact is limited to producing an output record with `authority` all false.

### 12. LOW — test coverage of new code path is thin

- Path: `test_schedule_contract.py`, `test_source_contract.py`. 14 pass (`cpu-tests.log`). Schedule functions are exercised directly. `audit_candidates.check_saved_lr`, `validate_metric_rows` schedule integration, `load_frozen` binding gate, `owned_processes_absent`, `build_binding` happy path, and `lr_schedule.apply_next_update_lr` / `new_schedule_state` are not exercised. Source tests are string-presence checks.
- Report wording is honest: it says the 14 controls are synthetic and source-only and do not establish runtime or training qualification. No overclaim found.
- Fix: add a synthetic `validate_metric_rows` and `check_saved_lr` test with minimal state dicts; add `apply_next_update_lr` round-trip and negative tests.

### 13. LOW — exact float equality ties producer to helper

- Path: `lr_schedule.py:27-33`. Schedule is computed as `START - DECAY_SPAN*(u-1)/59` with `DECAY_SPAN = START - END` (a computed float, may differ by an ulp from literal `2e-5`). Validators compare with `==`.
- Consequence: any runner that recomputes LR with the task's literal formula `3e-5-2e-5*(u-1)/59` could fail an exact-equality check. The runner must call `learning_rate_for_cumulative_update`.
- Fix: state in the r4 contract that LR must come from the helper, or compare with a tolerance of 0 against the helper value only.

## Required-check coverage (immutable prep, by reading)

| Requirement | Where | Status |
|---|---|---|
| Entry model/Adam/RNG exact restore | `validate_entry_state` 511-521, `audit_entry_restoration` 524-533 | preserved from predecessor |
| Savedmodel digests / fingerprints all six | `audit` 613-615 | preserved |
| Six candidates 324/336/348/360/372/384 | `UPDATES` line 54; loop `audit` 598-627 | preserved |
| Counters / episodes / journal prefix | `validate_state_identity` 363-389, `validate_resume` 402-432 | preserved |
| Raw-frame conservation | `validate_resume` 430-432 | preserved |
| Gradient and critic coverage | `validate_metric_rows` 311 (`validate_gradient_alignment`) | preserved; no separate critic-specific check in this file |
| Eval rows / deaths / Q1-Q4 means | `validate_certificate` 445-488, `performance` at 482 | preserved |
| Terminal exits / resources / reaping | `audit` 654-668, `wrapper.terminal_gates` 206-233, `owned_processes_absent` 236-252 | preserved |
| Cache / source strictness | `bind_environment` 124-134, `verify_pins` in wrapper 62-68, runner `verify_pins` 689 | preserved |
| Schedule metadata, origin, horizon, spec, group count | `schedule_contract._check_state` 37-53; `lr_schedule` constants 9-29 | new, correct per spec |
| Per-group saved LR at each candidate | `check_saved_lr` 280-289 → `validate_checkpoint_schedule` | new, checks every group |
| All 60 metric rows, group LR list, cum counter | `validate_metric_rows` 292-325 → `validate_metric_schedule`, `validate_progression` | new |
| Stale progress, missing LR, nonfinite, wrong origin | `schedule_contract.py` 39-95; tests 1-6 cover each | new, covered by synthetic tests |
| Helper computes on wrong counter | `learning_rate_for_cumulative_update` raises for `c <= 372`; `apply_next_update_lr` checks completed | new; see finding 9 for horizon |
| Retained incumbent 324 / 2939.40625 | `retained_best` 548-554, `BASELINE_MEAN_ALIVE` line 64 | preserved |
| Latest cost 10824.835578584221 (d3dd...) vs original 9758.365427209174 | constants 61-63; `validate_wall` 389-399 | new; the original 7c6f receipt is not pinned (noted, low) |
| Selected trajectory 5678.9823631240915 | line 60 | preserved |
| Observer path/hash exact | binding-driven (`audit_candidates.py:159-161`) | see findings 1, 5, 7 |
| Full mode parent-only, CLI refuses | `audit_candidates.py:706-707`, `wrapper.py:328-329` | CLI yes; in-process not enforced (finding 11) |
| Dynamic bindings immutable and hash-checked | `audit_candidates.py:144-161`, `binding_builder.py:45` | NOT MET (findings 1, 2, 5) |
| Module origins exact | `audit_candidates.py:21`, `schedule_contract.py:7` | NOT MET (finding 3) |

## Limits

- Not verified: runner r4 must emit metric-row fields `cumulative_updates`, `lr_schedule`, `optimizer_group_lrs`, and checkpoint fields `lr_schedule`, `inherited_counters`, `cumulative_counters`. The auditor fails closed if absent, but producer-side conformance cannot be checked without reading r4, which was prohibited. Needs a field-contract check before any run.
- Not verified: `lr_schedule.py` vs `35fee` predecessor helper beyond path-only claim (no diff run). Helper bytes match `ef81e875...` as recorded.
- Not verified: observer source `observe.py` (not in prep dir; loaded in full mode via `load_pinned_module`, which runs its module body in-process).
- Hashes below are recomputed read-only with `shasum -a 256`; no code executed.
- No CPU tests or subprocesses run. Test results cited from `cpu-tests.log` only.
- The 14-test claim is synthetic and source-only. It does not show the real six-candidate audit, the real checkpoints, or the real metric rows.

## Frozen source hashes (recomputed, match manifest values)

| File | sha256 |
|---|---|
| `audit_candidates.py` | `0f95cb1a87fbbee73a1d41b9f07ef330981a621ee4ca9f8d17eed44bb592b8b0` |
| `wrapper.py` | `4e14ae5b042b1b0ec39d95990235d0609d29f87dc4fbe4770dff159a00d9a22b` |
| `binding_builder.py` | `c28f15c1f388601830863bd60981b5aa368918aece1d34f5cac43d3748346573` |
| `schedule_contract.py` | `efaa421a3babbfd995074ae86c26731350d614dff7fdd34cefd4463e4cdf7809` |
| `lr_schedule.py` | `ef81e87580c39e6f733098a5c228e4660af03e7fccddcc06044e9d3612bce079` |
| `test_schedule_contract.py` | `e9302e2c3d465d9465963e09de50adea9959e3a7369fe9d915861a70809f7f6b` |
| `test_source_contract.py` | `c55efc4ba04e017e9b29a21b88eba22a65d057e6acbe00c44f4b3fc567ba0dbf` |
| `frozen-manifest.json` | `9b00f7758143671ad65d56a7797a77943ba24c2973d84d3c29f82dfa242ff70e` |
| `input-manifest.json` | `76e89ed89bdbd0e8a35a2d374619fdc7be89886ec39528eede3c9f7fadba5dea` |
| `output-manifest.json` | `d86d0cd213c7a2d6873a26271faf8f685b9ab163f48c70b2024299f8414e9147` |
| `report.md` (prep) | `3c271ab460684d6b39050717da066f18823d9a80e94380560cf38390b32904b3` |
| `cpu-tests.log` | `56fee6b4ad374a50d739c07d7a9daa15029a3fe63ea6cb9c78a310a9324f8721` |
| `auditor.diff` | `d137bb83103c2a1fca33e81f24f6e46ed3ec0db2d4723ae48b417b082c86234b` |
| predecessor `audit_candidates.py` | `1addab847a70adfdfa2585e837a9e964c15099786e47996c4087d8c6a5cb9719` |
| predecessor `wrapper.py` | `a915a4a07fbcae9a70948991a31ca5d334c9414ed7ca13ba8689af53ae5f5c06` |
| predecessor `full-audit.json` | `a897963fc5663ead1073bd6c936a026465cc408f378c2b3ecfea6842cc5b5b96` |

All thirteen prep-file hashes match the values in `frozen-manifest.json`/`output-manifest.json`/`input-manifest.json`. Predecessor hashes match `input-manifest.json`.

## Requested fixes before parent freezes binding

1. Pin `audit-binding.json` SHA explicitly and record it in outputs (finding 1).
2. Require explicit SHA for each auditor source in `binding_builder` or compare to `frozen-manifest.json` (finding 2).
3. Load schedule modules through pinned loader or assert their `__file__` and SHA (finding 3).
4. Restore constant assertions for parent, receipt, native, config (finding 4).
5. Pin `instantiation.json` (and `observation.json`) SHAs (finding 5).
