# Retained324 all-candidate auditor R2 — frozen source review (haiku, r1)

## Scope and method

- Static review only. No subprocess, no import of `dodge_rl`/torch, no test or bootstrap run, no MPS, no environment construction, no writes outside this directory.
- Reads were limited to the R2 auditor directory, the frozen prep `D2-retained324-continuation-prepare-luna-20261026-r2`, the observer source and `instantiation.json`, the immutable accepted parent `D2-retained300-continuation-20261026-r1` (JSON/JSONL/sidecar only; no `.pt` loaded), the parent terminal receipts, the predecessor `D2-retained300-all-candidate-auditor-luna-20261026-r5`, and the frozen runtime `dodge_rl` sources (static read only).
- Not read: `learning/runs/v2/D2-retained324-continuation-20261026-r1/` (current run) and mutable observer outputs (`launch.json`, `resources.jsonl`, `prelaunch.json`, markers, stdio). The observer directory is live: `launch.json` and the one-launch marker date from 13:41 and `resources.jsonl` was still growing. `observation.json` does not exist yet, so full mode cannot run yet.
- R2 CPU-control and bootstrap results are taken from `cpu-controls.log` and `bootstrap.json` by hash and content only. Nothing was re-run.

## Verdict

No blocking defect found by static review. Parent pre-invocation actions are listed at the end (finding 3 and the observer reap).

The full-mode path is the predecessor path that was already accepted. The predecessor `full-audit.json` (sha256 `e991bfd0…`) is the `full_audit_sha256` cited in the accepted parent completed-iteration receipt. It records `updates_audited` = [300, 312, 324, 336, 348, 360] and the full terminal gate keys. R2 differs from r5 by constants, observer instantiation wiring, one None/int check, and the parent-run identity (see Predecessor comparison). Findings 1–9 are hardening or latent issues. None was shown to accept wrong data or reject correct data on the expected run.

## Verified corrections (against immutable parent)

Checked against `D2-retained300-continuation-20261026-r1/development-000324.json` and `D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json`:

- Performance: alive Q1 `767.5`, Q4 `5468.6875`, mean `2939.40625`; score Q1 `4.09375`, Q4 `61.53125`, mean `29.53125`. Matches `audit_candidates.py:61`. The stale `1767.5` is gone.
- Deaths: 64 terminated, 0 capped. `normal_enemy` 35, `static_pattern_rect` 14, `kamikaze_enemy` 9, `kamikaze_explosion` 3, `moving_pattern_rect` 3. Matches `audit_candidates.py:62`.
- Parent identity: checkpoint `c10d90ec…`, sidecar `cedb2070…`, JSON `73f9ee72…`, JSONL `87773759…`, receipt `76cb1573…`, completed-cost receipt `7c6f250b…`, parent registration `8a60dc80…`, parent adapter `355880c2…`. All match the constants in `audit_candidates.py:36–47`.
- Clocks: `5678.9823631240915` (selected trajectory) and `9758.365427209174` (completed campaign cost) match receipt `wall_accounting` and completed-cost receipt. Match `audit_candidates.py:58–59`.
- `parent_run_id`: frozen `runner.py:738` writes `D2-retained300-continuation-20261026-r1`. Matches `audit_candidates.py:45` and the check at `audit_candidates.py:285`. The predecessor wrote `D2-retained276-lr3em5-20261026-r2`, so this is a real fix.
- Phases: `UPDATES` = 324, 336, 348, 360, 372, 384 (`audit_candidates.py:51`). Same as runner `EVALUATION_UPDATES` and registration `evaluation_updates`.
- Outputs: 32 expected names (8 fixed + 6 × 4 per update). Equal in `audit_candidates.py:expected_outputs()`, `runner.py` `validate_registration`, and `registration.json` `expected_outputs`. The audit checks equality at full mode.
- Registration: sha `44ac8185…`; `pins` = 13846; `forbidden_outputs` = `['lr-transition.json']`; `run_seed` 4200000001; `expected_lease` run_id `D2-retained324-continuation-20261026-r1`.
- Stale-path check: `grep` over R2 `.py`/`.md`/`.json` for `300|301|312|276|lr3em5` shows only correct parent-lineage references. No stale phase fixtures.

## Coverage of the requested checks

- State, model, Adam, RNG, counters, episode indices: `validate_state_identity` (`audit_candidates.py:268–320`), `validate_resume` (`:336–366`), `validate_entry_state` (`:444–454`), `audit_entry_restoration` (`:457–466`). The same rules exist in the frozen launcher (`execute_once.py:88–285`) and worker (`runner.py:632–832`). Full mode also runs `launcher.validate_outputs`.
- Gradient coverage and metric chain: `validate_metric_rows` (`:241–261`) and `runner.validate_gradient_alignment` (`runner.py:406–447`).
- Raw-frame conservation: `validate_resume` (`:364–366`), same identity as `execute_once.py:277–279`. Entry case is `0 == sum(abandoned gameplay_frames)`. Holds if fresh-env gameplay frames are zero. The predecessor passed this rule on the 300 run.
- Observer wiring: full mode checks observer directory, source digest `1f991a9a…`, `instantiation.json` digest `4ce6cb20…` (matches my hash), schema, `actual_launches == 0`, `one_shot_marker_absent` (`audit_candidates.py:511–519`). It then loads the observer source and checks `REG_SHA` (`:514–515`). Terminal observer fields are checked at `:585–603`.
- Reaping, resources, cache, no LR transition: observer postflight (`observe.py:291–311`), wrapper `terminal_gates` (`wrapper.py:179–206`), `owned_processes_absent` (`wrapper.py:209–225`), auditor-owned empty bytecode prefix, `lr-transition.json` absence (`audit_candidates.py:575`). Registration cache prefix is `PREP/empty-pycache`; auditor override is `OUT/empty-pycache`.
- CLI refusal: `audit_candidates.main` (`:626–638`) and `wrapper.main` (`:293–303`) both refuse without `--provisional`. `full_mode` is only reachable from Python.
- Parent-only invocation (`future-parent-full-mode.md`): interpreter path, `-B`, `PYTHONPYCACHEPREFIX`, `env -u PYTHONPATH`, `observer_dir`, and `name` match the wrapper binding gates.

## Findings

Severity is for the parent. Static only; nothing executed.

1. **low — `wrapper.py:217–223` with `observe.py:181,184`.** `outer_process_group` is not an owned group. The observer spawns the launcher without `start_new_session` (`observe.py:181`), so the recorded pgid is the observer's inherited group. The wrapper then calls `os.killpg(pgid, 0)`, which fails if any live process shares that group. Consequence: false block after a successful run (`WrapperError`), no full-audit record. No false acceptance. The predecessor had the same check and it did not trigger. Fix: drop the outer-group check (`outer_process_absent` already covers the process) or record the group only when the launcher leads its own session.

2. **low — `wrapper.py:213`.** `os.kill(observer_pid, 0)` succeeds for an unreaped zombie observer, which gives a false "still exists" block. `PermissionError` is not caught. Consequence: false block only. Fix: reap the observer before the wrapper runs (parent step) and catch `PermissionError`.

3. **medium — process gate, `wrapper.py:35,269,288`.** Only `audit_candidates.py` is pinned (`AUD_SHA`). Nothing pins `wrapper.py` or `bootstrap.py`. `wrapper_sha256` is recorded at `wrapper.py:269` but never compared. `full_mode` is an ordinary importable function; "parent-only" is only convention. Consequence: a wrapper edited after review (e.g. gate thresholds) would still produce an accepted-looking record. Condition for the parent: before invoking `full_mode`, verify `sha256(wrapper.py) == a915a4a07fbcae9a70948991a31ca5d334c9414ed7ca13ba8689af53ae5f5c06` and `sha256(bootstrap.py) == f07980868ad0e7f0da1077daebf109812de6150f32b34e707c2faa8d3399123f`, and record both in the parent receipt.

4. **low — `audit_candidates.py:526–558, 577–585`.** Full mode does not check `artifact-manifest.json` (written by the launcher before `execution-result.json`) against final bytes. It does not reject unexpected files in the run directory (only missing ones, `:577–578`). It reads `worker-result.json`, `execution-result.json`, `observation.json` without hash-tracking them (`wrapper.py:251–253`, `audit_candidates.py:579–585`). Consequence: later edits to these receipts would not appear in the record. Fix: track them and verify `artifact-manifest.json` entries.

5. **low — `audit_candidates.py:84–88, 500–501`.** `read_stable` reads twice and raises if the file changed between reads. A provisional audit of a live run can fail spuriously if the worker appends during the check. Full mode is not affected (journals are complete).

6. **low, label only.** The handoff label "SHA1 `addab847…`" is wrong: `1addab847a70adfdfa2585e837a9e964c15099786e47996c4087d8c6a5cb9719` is SHA-256 (64 hex). SHA-1 of `audit_candidates.py` is `8beac02eaeccd64997625e000b234bc59e62d082`. The wrapper pin and manifest use SHA-256 correctly.

7. **low — tests, `test_source_contract.py:49–54, 24`.** `test_wrapper_hash_and_cli_refuses_full_mode` never hashes `wrapper.py` (it checks `AUD_PATH`). `test_registered_sources_and_own_bytecode_prefix` asserts a text substring (`"PYTHONPATH must be unset"`) rather than behavior. No negative control for `parent_run_id`, a wrong observer digest on the full path, or `outer_process_group` None. Passing tests here do not prove those properties. Fix: rename, and add behavioral negatives.

8. **low — cosmetic, `audit_candidates.py:241–246`.** The docstring sits after a `check`, so it is a dead string; the `len(metrics) >= max_local` check appears twice.

9. **info — None handling, `wrapper.py:217–223` vs `audit_candidates.py:590–591`.** Wrapper skips None; audit requires `int`. Net effect: None blocks in full mode. Harmless; align the two.

Additional info (not blocking): `audit_candidates.main` and `wrapper.main --provisional` take different import-strictness paths (the wrapper applies `make_strict_import_runtime`; the CLI relies on `import_runtime`'s origin check). Full mode is wrapper-only. Entry raw-frame conservation (`audit_candidates.py:364–366`) depends on fresh-env gameplay frames being zero; supported by `identity.py:230` and `ppo.py:354` patterns and by the predecessor's accepted 300 run. Not runtime-verified here.

## Predecessor comparison (`D2-retained300-all-candidate-auditor-luna-20261026-r5`)

- Auditor and wrapper: differences are constants and identifiers (300 → 324 names, hashes, clocks, baselines, performance, death causes, pin count 13827 → 13846), the observer instantiation wiring (`audit_candidates.py:511–519`), and the None/int check (`:590–591`). `wrapper.py:217–223` adds None-skip.
- Observer source: `observe.py` differs from r5 only by constants (BEST300 → BEST324, pins 13827 → 13846, eval updates, registration path and sha).
- Frozen runner: differs from r5 only in constants, the parent-receipt validator (`runner.py:194–246`), and `parent_run_id` (r5 `D2-retained276-lr3em5-20261026-r2` at line 776 → `D2-retained300-continuation-20261026-r1` at line 738). The worker body is otherwise identical.
- Frozen launcher: `execute_once.py` is byte-identical to r5 (`7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e`).
- Evidence: r5 `full-audit.json` (sha `e991bfd0…`) is the full audit cited by the accepted parent. Its record has `mode: full_parent_only`, six updates, `proposed_best_update` 324, and the full terminal gate keys.

## Hashes (sha256)

Auditor directory (`D2-retained324-all-candidate-auditor-luna-20261026-r2`):
- `audit_candidates.py` `1addab847a70adfdfa2585e837a9e964c15099786e47996c4087d8c6a5cb9719` (sha1 `8beac02eaeccd64997625e000b234bc59e62d082`)
- `wrapper.py` `a915a4a07fbcae9a70948991a31ca5d334c9414ed7ca13ba8689af53ae5f5c06`
- `bootstrap.py` `f07980868ad0e7f0da1077daebf109812de6150f32b34e707c2faa8d3399123f`
- `test_audit_candidates.py` `e19b0d878528bc3570021f852977bbfb35085967d18bc09a1060addcf7205dce`
- `test_source_contract.py` `b53e442617066b392e02008ba0fd6a6ec2380efa26615ea920adc04ec56f6b64`
- `report.md` `2a57c535e0872b052e494963e9a352d6d633c58271e6a53f36d70cf05a3b3765`
- `output-manifest.json` `7dddb60e2f78c1f50ce0f0012a4625cad02012ee2490a4d3351e706911cf865d`
- `cpu-controls.log` `0bda9c8cc5e7bf8683c1d6775fdc3f4a1fd40ac37d3e1b42fab07fb81eb33fdb`
- `bootstrap.json` `dee75085c8dbe9f4a9cf32c27bc6803ec4d53c3f5f94f5744ecbd58161187488`
- `bootstrap.log` `d1913b411e4988abfee10a7d1a66f7756b029776f5c6052f53c7fc7579f7d86e`
- `input-manifest.json` `49500167b4afa8a6516d4f2263e4cb552682115506449a68c65ada138c286e5a`
- `future-parent-full-mode.md` `96cb5346e50f59a444528fe980d370831ee352f817384f2bf588c6e094569be7`

Frozen prep (`D2-retained324-continuation-prepare-luna-20261026-r2`):
- `registration.json` `44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a`
- `registration_schema.py` `87497edebf9f94f705b73fb899b1f290d96d8de2a0e66e28c30c75983ca2f57f`
- `parent_adapter.py` `355880c2cddc455219c4714b8fd57b7a59075ef0581086b153d7b89b05a26a26`
- `runner.py` `43e93f7469c8dc3b0719f8f218ccb7f58f6860fcd5e0625e0fa580320d7e0c10`
- `execute_once.py` `7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e`

Observer source (`D2-retained324-execution-observer-parent-20261026-r1`):
- `observe.py` `1f991a9a984b18eb8861248ef45b285bdd6288b9e80f5a209af61e15a371f71b`
- `instantiation.json` `4ce6cb2058db22f2aa6ee6f5ec8c745deb5a1a535030ccb591c638a8e75931fd`

Parent (immutable accepted, `D2-retained300-continuation-20261026-r1` and terminal audit):
- `development-000324.json` `73f9ee722b445ae8e2baf2b16fcb40744338323ec17efe35a56e703947a35e64`
- `development-000324.jsonl` `8777375952d4c656ff805f8c08da30d62e8185cdea5f63e3f0e98f542ff23215`
- `checkpoint-000324-candidate.pt` `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`
- `checkpoint-000324-candidate.pt.json` `cedb20704c9a7c0ec9126c6e7da2f75e230d6acdaa1b7b47f25256ed4f1fd939`
- `retained-best-candidate-receipt.json` `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`
- `completed-iteration-receipt.json` `7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b`
- parent registration `8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79`
- predecessor `D2-retained300-all-candidate-auditor-luna-20261026-r5/full-audit.json` `e991bfd0d1177cb32c10d9879d8f362a8d51e6f5cfa9e14c051e54010964cf46`

## Parent actions before full invocation

1. Verify wrapper and bootstrap sha256 (finding 3) and record them with the audit receipt.
2. Confirm the observer and launcher writers are reaped, and reap the observer process before calling `full_mode` (finding 2).
3. Decide on findings 1, 4, 7 before acceptance. Each is hardening, not a correctness blocker.
