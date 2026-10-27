# Independent source review: paired LR upper-D64 evaluator r2

Reviewed frozen target: `learning/runs/v2/paired-LR-upperD64-evaluator-luna-20261026-r2/` (source SHA-256 `3263459ceb66eec189957931bcc389dbf1e43a391863d5a1f98b5a9b490557b6`).
Scope: source, tests, log, manifests, report, README, and the native/trainer/endpoint records that the evaluator must bind. Read-only. No imports, tests, subprocesses, checkpoint loads, MPS, evaluation, leases, or shared-state edits. Only this directory was written.

## Verdict

**Not ready for an actual evaluation.**

- **Complete helper:** yes, for the CPU-fake path. `paired_eval.py` implements the r1 fixes (B1–B7, S1–S3) at the source level, and the native-facing call shapes match the Python and Rust APIs I checked.
- **Runtime qualified:** no. The native path has never run against a real `VecDodgeEnv`, real checkpoint bytes, or real endpoint metadata. The evaluator also cannot yet bind the native extension that both arm trainings used (B-A below).
- **Blockers before any evaluation:** B-A and B-B. B-C should be fixed before the parent is handed the module. B-D is cheap and should be fixed with them.

## Blockers and gaps

### B-A — HIGH: native binding cannot reproduce the training native

- Facts:
  - Repo root `python/dodge_rl/_native.cpython-312-darwin.so` SHA-256 starts `967c7249…`. This matches `identity.py:24` `EXTENSION_SHA256` and the registrations' `native.old_sha256`.
  - Frozen trainer runtime `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/_native.cpython-312-darwin.so` starts `022d41dd…`.
  - Both arm trainings used `022d41…`:
    - Linear: `D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json:148-152`.
    - Constant: `D2-retained324-continuation-prepare-luna-20261026-r2/registration.json:95-99`.
  - All other checked Python sources match byte-for-byte between repo root and the frozen tree: `models/teacher.py`, `dev_eval.py`, `identity.py`, `checkpoints.py`, `__init__.py`. Only the `.so` differs.
- Path: `paired_eval.py:344-363` (`_verify_runtime_pins`), `:366-369` (`source_root` is caller-supplied but layout is hardcoded), `:414-418` and `:458-462` (`root/"python"`, `root/"python/dodge_rl/__init__.py"`), `:434-437` and `:473-476` (native pin vs registration).
- Layout: the code requires `python/dodge_rl/`, `crates/**/*.rs`, `Cargo.toml`, `Cargo.lock`, and `docs/v2-m3-run-protocol.json` under one root. The frozen r5 tree has only `own/runtime/dodge_rl/` and `own/docs/`. It has no `python/` level, no crates, and no Cargo files. Pointing `source_root` at it fails closed (`pinned runtime file missing`). Pointing it at repo root with `022d` pins also fails closed (`pinned runtime file changed`).
- Trigger: the parent writes registration pins to whatever is in repo root now (`967c…`). The evaluator then runs with a native the trainings did not use, with no error.
- Consequence: nothing in the code links the evaluation native to the training native. The "same native/config/model/source as both arms" requirement is not enforced.
- Also: the required Rust source pins are current working-tree files. Repo `git status` shows modified and untracked crate sources. Whether those sources reproduce the `022d` build is unverified.
- Fix: register the training native SHA (`022d…`) explicitly in the registration. Build the runtime from a layout adapter that maps the frozen tree onto the required layout, or make the layout a registered field. Assert that `native` matches the training registration for both arms. Do not change repo root `python/dodge_rl/_native…so` as part of this; that is a parent decision.

### B-B — MEDIUM-HIGH: endpoint metadata contract matches no existing artifact

- Path: `paired_eval.py:168-173` (`validate_registration` reads `phase_update`, `cumulative_updates`, `run_id`, `checkpoint_sha256` from metadata), `:379-384` and `:399-406` (`metadata_sha256` and `model_state_dict_sha256` pins required).
- Facts: the existing endpoint sidecars `D2-retained324-continuation-20261026-r1/checkpoint-000384-candidate.pt.json` and `D2-retained324-linear-lr-20261026-r1/checkpoint-000384-candidate.pt.json` contain only `checkpoint_sha256`, `eligibility_status`, `promoted`, and `training_eligible`. No `run_id`, phase, or cumulative-update fields.
- Also: no file in the repo records `model_state_dict_sha256` for either endpoint. Producing it requires deserializing the checkpoint, which is a separate parent-authorized step.
- Trigger: the parent registers the real sidecar bytes → the metadata check fails closed (`checkpoint endpoint metadata differs`). Or the parent authors a new metadata file to satisfy the schema.
- Consequence: the run identity and update claims are not cross-checked against the loaded checkpoint. `checkpoint.state["identity"]` and `state["counters"]` (`checkpoints.py:72-80`) are never compared to metadata.
- Fix: define a parent-produced endpoint metadata schema. Derive `run_id`, updates, and `model_state_dict_sha256` from the loaded checkpoint's `identity` and `counters`, and require equality.

### B-C — MEDIUM (HIGH if used): `evaluate_registered` still trusts caller claims

- Path: `paired_eval.py:177-208`. The `collector is None` branch (`:189-193`) runs the native collector with a caller-supplied `model` and caller-supplied `checkpoint_metadata`. Only `validate_registration` (`:185`) checks the claimed SHA and run ID. No file bytes or state-dict hash is checked.
- Trigger: the parent calls `evaluate_registered(model=<any model>, checkpoint_metadata={"checkpoint_sha256": <pin>, …})`.
- Consequence: a different checkpoint is attributed to the pinned endpoint. This is the r1 B5 issue, which is closed only in `evaluate_with_registered_backend`.
- Fix: remove the function, make it private, or route it through `build_registered_backend`.

### B-D — LOW-MEDIUM: seed manifest bytes checked after collection, not before

- Path: `paired_eval.py:496-510` (`evaluate_with_registered_backend` never calls `load_manifest()`). The manifest is checked only in `validate_rows` (`:55-56`, called at `:305` and `:509`), i.e. after all 64 environments have run.
- Consequence: a modified manifest wastes the run. No output is published on failure, so this is not a false result. It does contradict the README claim that all pins are checked before environment creation.
- Fix: call `load_manifest()` before `check_guard()` at `:503`.

### Notes (not blockers)

- **Excluded seed ranges are inert.** `crates/dodge-rl-env/src/seed.rs` `seed_for`, Evaluation arm, returns the seed without a range check. The training-excluded label therefore rests on the manifest and protocol, not on native enforcement. Protocol ranges (`docs/v2-m3-run-protocol.json:108-115`) match the three `EXCLUDED_SEED_RANGES` in the code, and the upper-D block `3489660992..3489661055` lies inside `[3489660928, 3489661055]`.
- **Import before origin check.** `import dodge_rl` loads `_native` through `python/dodge_rl/__init__.py:3`. The native bytes are pinned before import (`:360-363` and `:436-437`), so this is only a side-effect ordering issue for a wrong-origin module (`:418`, `:462`). LOW.
- **Thread count not enforced in code.** The README asks for one torch thread. No `torch.set_num_threads` is present. It depends on the environment variables only. LOW.
- **`summarize_arm` default `allow_unavailable=True`** (`:107-108`). The native path rejects `unavailable` earlier (`:305`), so the production path is safe. The injected-collector path is not.
- **Device scope.** `collect_d2_rows` requires `device == "cpu"` (`:215`). The RNG snapshot covers Python, NumPy, and torch CPU only. A future MPS scope would need a `torch.mps` RNG capture and a device-specific guard. Not in scope now.

## Verified against actual source (not just r2 claims)

- **Constructor.** `VecDodgeEnv` signature (`crates/dodge-rl-env/src/python.rs:273-290`) accepts all twelve keyword arguments used at `paired_eval.py:231-234`. `seeds_by_slot` is `Vec<Vec<u32>>` and `excluded_seed_ranges` is `Vec<(u32,u32)>`. Both match.
- **Step.** `step` takes an `i64` array of length `slots` (`env.rs` `step`). It returns `info` for every slot each call (`env.rs` `step`, `python.rs:172-186`), so `result["info"][0]` is valid on every step.
- **Info fields.** `seed.evaluation`, `seed.actual_seed`, `startup_frames`, `gameplay_frames`, `alive_frames`, `score_raw_fixed`, `score_delta_sum_raw_fixed`, `objective_return`, `bootstrap`, `terminated`, `truncated`, and the `death_*` keys exist in `python.rs:86-127`.
- **Observations.** The four keys in `identity.py:25` match `python.rs:144-147`. `observations()` and `step()["observations"]` return shape `[B,…]`.
- **Model.** `OmniscientEntityTeacher()` takes no arguments (`teacher.py:81`). `forward(global_feats[B,1,14], entity_feats[B,80,16], entity_types[B,80], entity_mask[B,80])` returns `TeacherOutput.logits` (`teacher.py:145-174`). Action count is 9 (`dodge-core/src/action.rs:20`).
- **Checkpoint loader.** `load_checkpoint(path, expected_identity=None, expected_sha256=None)` (`checkpoints.py:112`) checks the file hash, then unpickles. `make_state` stores weights under `"model"` (`checkpoints.py:72-80`). The file-byte check at `paired_eval.py:396` and the loader's own check on the same read give no TOCTOU gap.
- **Frame semantics.** Death frame is not counted alive (`env.rs` `advance`). `fatal_gameplay_frame = gameplay_frames` at death (`env.rs` `death_info`). Cap truncation fires at `gameplay_frames >= raw_frame_cap` on a live frame, and 18000 is divisible by 4. The `validate_rows` rules at `paired_eval.py:71-75` match.
- **Objective.** `env.rs` `info`: `score_delta_sum/65536 + alive/100 − 5·terminated`, the same formula as `paired_eval.py:82` and `:261`.
- **Startup.** Pinned at 13 (`env.rs` `start`).
- **Constant endpoint.** `e25117bf…199b` matches the constant continuation's `checkpoint-000384-candidate.pt.json` and the parent terminal audit receipt (`D2-retained324-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json`, `endpoint_checkpoint_sha256`). The sidecar label is still `provisional_pending_parent_terminal_receipt` with `training_eligible: false`. The audit status is `accepted_completed_training_iteration_no_best_replacement`. No contradiction, but the endpoint is not promoted.
- **Linear endpoint.** The on-disk linear 384 sidecar shows `cc5c3bee52b3fdad925ad90e793983df41954f16ce11403f9f32c431434e52e2`, run `D2-retained324-linear-lr-20261026-r1`, same provisional label. This is not `384e7…`. Its SHA appears in linear run artifacts and `D2-retained324-linear-auditor-prepare-luna-20261026-r3/full-audit.json`. No parent receipt binding it was found. The design (`paired-LR-upperD64-evaluation-design-parent-20261026-r1/design.json`) leaves the linear checkpoint SHA null.
- **Parent.** Both arms branch from `c10d90…` (`selected` 324, `registration-final-r2.json:17,30,54`). No best-348 substitution in the code.
- **Seed manifest.** `e11e9d6a…c886c`, ascending `0xD0000040..0xD000007F`, `training_excluded: true`, `prior_nonuse_proven: false`, `qualification_or_sealed_claim: false`. Labels match the design. Not sealed, not proven independent.
- **Protected root README** `be478416…` unchanged.

## r1 finding closure

| r1 item | r2 status |
|---|---|
| B1 null SHA/run ID | Closed in `validate_endpoint` (`:144-151`) and the backend path. Open in `evaluate_registered` through caller claims (B-C). |
| B2 frame conservation | Closed (`:71-75`). |
| B3 fixtures | Closed (`test_paired_eval.py:10-21`). |
| B4 collector adapter and kwargs | Closed for the native path (`evaluate_registered` calls `collect_d2_rows` with matching kwargs). Injected-collector path retained for fakes. |
| B5 caller claims | Closed in `build_registered_backend` (file bytes, metadata bytes, state-dict hash). Open in `evaluate_registered` (B-C). |
| B6 overwrite | Closed (`_write_exclusive_json` `:319-333`, `os.link`). |
| B7 unavailable cause | Closed for native collection (`:305`). |
| S1 RNG/weights/grads | Implemented (`:219-302`), CPU only. |
| S2 arm provenance | Summary records both checkpoint SHAs, run IDs, and registration SHAs. |
| S3 startup/score recording | Recorded in completed rows (`:268-269`). |

## Tests and logs

- `cpu-tests.log`: 11 unittest cases, all `ok`. Re-hash matches `artifact-manifest.json` (`cf57819d…`). Fake environments and fake policy only. I did not re-run them.
- `paired_eval.py` hash `3263459c…` and `seed-manifest.json` hash `e11e9d6a…` match the manifest.
- Coverage gap: no positive test of the injected-backend pin path (`injected_backend_reviewed: true` with matching callback identities), and no negative test for B-A layout or native mismatch.

## Parent-owned inputs still required

1. A registration that pins the training native `022d…` explicitly and binds it to the frozen runtime layout (B-A).
2. Endpoint metadata matching the schema, with `run_id`, updates, `model_state_dict_sha256`, and metadata SHA, derived from the loaded checkpoint (B-B).
3. Confirmation or acceptance of the linear endpoint receipt. The constant endpoint is pinned. Linear is `cc5c3bee…` on disk and unbound.
4. A runtime resource budget and guard active before, during, and after the call.
5. An explicit execution decision.

## Limits

- Read-only. Nothing was imported, run, or constructed. Native behavior is inferred from Rust and Python source.
- Checkpoint binaries (`*.pt`) were not opened, hashed, or deserialized. Sidecar JSON values are claims, not verified against bytes.
- Hashes of `.so` and source files were computed with `shasum` (read-only).
- The CPU test log is accepted as recorded. The interpreter header is absent, so the environment used is unverified.
- Repo `git status` at session start shows modified and untracked crate sources. Whether they reproduce the `022d…` native build is unknown.
- Seed label: "unselected training-excluded upper-D development block; prior nonuse not proven". Not sealed or independent.
- Comparison remains diagnostic: one paired training seed `4200000001`, linear average LR `2e-5` vs constant `3e-5`, fixed update-384 endpoints. No schedule-causal claim. No real-game timing or resource qualification claimed.
- No subdelegation.
