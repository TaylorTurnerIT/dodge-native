# Independent source-only review: D2-retained324-linear-registration-luna-20261026-r1

Scope: read-only review of `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-registration-luna-20261026-r1/{parent_adapter.py,registration_schema.py,build_registration.py,test_registration.py,source-manifest.json,tests.log,README.md,implementation.diff}`. Runner r3 not read. No imports, tests, subprocesses, checkpoint loads, lease/state reads. Hashes below are recorded values, not recomputed (no hashing tool run).

## Verdict

Not approved for final registration. Source fails closed: `build_registration()` raises before any output when runner/helper/launcher manifests are absent, and `main()` writes only via exclusive create. Emission is correctly blocked. Source has two high-severity integration gaps and several medium gaps listed below. The 12 CPU checks in `tests.log` are recorded only; not reproduced here.

## Missing required deliverables (distinct from source defects)

1. Successor launcher `execute_once.py` in own-output dir: absent. Required by `build_registration.py:74-78`.
2. Runner r3 manifest (`runner_manifest_received: false` in `source-manifest.json`): absent.
3. Schedule-helper manifest: absent.
4. Launcher manifest: absent.
5. Final `registration.json`: absent, intentionally (confirmed by Read miss).
6. Runner r3 / `lr_schedule.py`: not read by policy; helper digest only asserted against constant `35fee3a7...`.

Consequence: no registration can be emitted. This is expected, not a regression.

## Source findings (ranked)

| # | Sev | Location | Finding | Trigger | Consequence |
|---|---|---|---|---|---|
| D1 | HIGH | `build_registration.py:106-109` (only producing/latest validated); `parent_adapter.py:84` `validate_parent` | Registration builder never calls `validate_parent`. Only test calls it (`test_registration.py:67`). The strict parent contract (model/Adam/RNG fingerprints, counters, episode indices, config/runtime/native/policy/registration SHAs, optimizer lr/eps) is not enforced on the path that authorizes a registration. Registration also does not embed those fields from selected receipt. | Valid receipts/manifests with a checkpoint state that differs from selected324. | Registration can bind to wrong parent state with correct receipt digests. Enforcement depends on an unverified runner caller. |
| D2 | HIGH | `build_registration.py:90-91` | `BASE/registration.json` and `BASE/source-manifest.json` are read with no digest pin, unlike runner/helper/launcher manifests. The 13846-pin set and `historical_R1_pin_coverage` (`removed_R1_pins: 0`, `shared_hash_rewrites: 0`) are self-reported and trusted. | Any drift in r2 base files. | Historical pin drift propagates silently into final pin set; preservation claim is not independently checked. |
| D3 | MEDIUM | `build_registration.py:202-206` | `resource_cost_anchor` points to producing receipt (before 8621.338345875141 / after 9758.365427209174). New treatment cost chain should continue from latest after 10824.835578584221 (`latest_resource_cost_anchor` at lines 153-158 is correct but secondary). | Any consumer that reads `resource_cost_anchor` as baseline. | Treatment resource accounting understated by 1066.4701513750479 s. Violates the stated producing-vs-discarded separation. |
| D4 | MEDIUM | `build_registration.py:10-11`; hashes at `:139-142`; test imports `test_registration.py:13-15` | Bare imports `import parent_adapter` / `import registration_schema`. Recorded `parent_adapter_sha256` hashes `OWN/parent_adapter.py` path, not the module actually loaded (`parent_adapter.__file__`). | A different `parent_adapter` earlier on `sys.path`. | Registration records a digest of a file that was not executed. Origin binding not asserted. |
| D5 | MEDIUM | `build_registration.py:84-86` | `schedule_spec_sha256` accepted if any 64-char string. Exact match to `7ceed85c...` only enforced in `registration_schema.validate_identity` (`registration_schema.py:289-291`), and only called from `main()` at `build_registration.py:240`. | Direct programmatic call to `build_registration`. | Unvalidated spec digest can reach in-memory registration. |
| D6 | MEDIUM | `build_registration.py:185-190`, `:191-196` | Hard-coded authority literals written into registration: `expected_lease.authorization: "user_continue_D2_training_v3"`, `launcher_module_contract.status: "immutable_successor_launcher_manifest_verified"`. Builder verifies neither. | Any valid manifest set. | Registration asserts authority/verification it did not perform. Runner may treat text as authority. |
| D7 | MEDIUM | `build_registration.py:121`, `:124-197` | `registration = deepcopy(base)` then `.update()` only named keys. Unrelated keys from r2 survive unfiltered. `registration["parent"]` at `:198` raises `KeyError` if base lacks `parent`. | Base shape differs from assumed. | Stale continuation fields can leak into treatment registration; unverified because base is unpinned (D2). |
| D8 | MEDIUM | `build_registration.py:200-201` | `parent.completed_iteration_receipt_*` set to producing receipt (retained300). Latest terminal (retained324) is the accounting receipt for the discarded branch. Mapping is ambiguous. | Consumer reads parent completed-iteration as terminal audit. | Producing vs terminal conflation, same class as D3. |
| D9 | MEDIUM | `registration_schema.py:24-55` | `validate_identity` does not check resource limits (1750/1790/1800/10 cleanup, 6 GiB RSS/MPS), PPO settings, lease, or presence of runner/helper/launcher pins. README claims "Preserve other PPO settings" and "limits unchanged" with no code enforcing them. | Any registration with altered limits/PPO. | Claim not backed by source. |
| D10 | LOW | `parent_adapter.py:79-80` | `abs_tol=1e-12` on values near 1e4. Double ULP there is ~1.8e-12, so tolerance is below representable resolution. Current constants pass only because of their exact binary values. | Recomputed or re-serialized receipt. | Fragile; may spuriously fail or accept by one ULP. |
| D11 | LOW | `build_registration.py:16`, `:18` | `SCHEDULE` constant unused in builder (only patched in test). Test imports `importlib` unused (`test_registration.py:6`). `validate_identity` with missing `root` resolves `Path("")` to cwd (`registration_schema.py:269`). | — | Dead/cwd-dependent code; no current exploit. |
| D12 | LOW | `build_registration.py:97-101` | `historical_R1_pin_coverage` check compares manifest's self-declared numbers to constants. Does not recompute from R1 data. | — | Same as D2. |

## Test/evidence gaps

- No test for `_source_pin` rewrite refusal (`build_registration.py:52-58`).
- No test for output collision refusal, CLI `main()` exclusivity, runner-dir mismatch, helper-name mismatch, launcher-dir mismatch, launcher `runner_module_path` mismatch, schedule spec digest mismatch, or base-digest drift.
- No test of the linear schedule formula (helper not in review set).
- Fingerprint tests reuse identical fixtures (`test_registration.py:56-59`); mismatch path for optimizer/RNG/model fingerprints not exercised.
- `ParentAdapterTests.selected_state()` hard-codes `current_iteration_observed_outer_seconds=488.7727023329353` and computes the cost-lineage expectation with the same formula as the adapter (`test_registration.py:46-48`). Lineage check is tautological under test.
- Tests read real receipts from `V2/...` (`test_registration.py:19-21`) and copy base files (`:188-191`). Not hermetic.
- `test_builds...` asserts `13846 + 10` pins. Arithmetic: 3 own modules + 3 runner/helper/launcher + 3 manifests = 9 new paths; the +10 implies exactly one of three receipt paths already pinned in base. Data-dependent, not an independent check.
- `tests.log` has no command, timestamp, or exit code. 12 `ok` lines counted; not reproduced.

## Constants checked against stated values (source only)

Matches stated values: selected receipt `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`; checkpoint `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`; producing receipt `7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b` (before 8621.338345875141, after 9758.365427209174); latest receipt `d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3` (before 9758.365427209174, after 10824.835578584221, outer 1066.4701513750479); trajectory 5678.9823631240915; schedule spec `7ceed85c5dc277602f2f51937b4ac003e2013e2689341a963ce5d82d5b64c9e4`; helper `35fee3a73fc1b283c5412d577ccee8635caa26f6fbf251e10009566c3a18fbc6`; run ID `D2-retained324-linear-lr-20261026-r1`; seed `4200000001`; cum 372→432; phase 324→384; LR 3e-5→1e-5, formula gives 3e-5 at u=1 and 1e-5 at u=60.

Not given in brief, not verified against any source here: config `1c24df3e...`, checkpoint metadata `cedb2070...`, parent-of-run `e2c8fbe4...`.

Accounting separation: producing chain (`validate_producing_cost_receipt`) and latest chain (`validate_latest_cost_receipt`) are separate. Latest before equals producing after (`parent_adapter.py:157`). No `competence_passed` key is required or accepted on latest (`parent_adapter.py:75-76`). Trajectory baseline unchanged. D3 is the exception: the registration's named cost anchor is the producing receipt.

Source origin: builder hashes OWN files by path, not loaded module (D4). Runner, helper, and launcher are bound by explicit manifest digests, trusted only via manifests (manifest claims such as `runner_module_plumbing` are not checked against launcher bytes).

## Incident scope

Not evaluated here. Source-validity findings are independent of the README clobber incident and the recovery record `README-recovery-parent-20261026-r1/receipt.json`. Root README was not touched.

## Required before final registration

1. Enforce `validate_parent` (or an equivalent state/fingerprint contract) on the emission path, or embed the selected receipt's fingerprint/counter fields in the registration and check them at runner start (D1).
2. Pin `BASE/registration.json` and `BASE/source-manifest.json` by digest; recompute historical pin coverage (D2).
3. Point `resource_cost_anchor` at latest after-cost chain, or rename/relabel explicitly (D3).
4. Assert `parent_adapter.__file__` / `registration_schema.__file__` equal OWN paths before hashing (D4).
5. Validate spec digest in builder, not only in `main()` (D5).
6. Remove hard-coded authority/verification literals or derive them from verified inputs (D6).
7. Build registration from an explicit key whitelist, not base deepcopy (D7).
8. Resolve `parent.completed_iteration_receipt` meaning (D8).
9. Check resource limits, PPO settings, and runner/helper/launcher pins in `validate_identity` (D9).
10. Add tests for D1-D9 negative paths; make tests hermetic; remove tautological lineage expectation.
11. Supply the successor runner r3 manifest, helper manifest, launcher manifest, and `execute_once.py` (missing deliverables).

No runtime, training, lease, or checkpoint claims are made here.
