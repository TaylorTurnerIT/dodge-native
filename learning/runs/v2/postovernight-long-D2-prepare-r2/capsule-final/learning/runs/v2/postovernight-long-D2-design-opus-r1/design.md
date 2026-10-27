# Long bounded D2 experiment — design (Opus r1)

Status: design only. No training, gameplay, inference, Torch/native import, checkpoint
deserialization, test, source/config/ledger/doc edit or child delegation occurred.
The parent owns the final registered protocol, lease, state and docs. Machine-readable
contract: [plan.json](plan.json). Input hashes: [evidence/manifests/inputs.json](evidence/manifests/inputs.json).

## 1. Decision summary

| Item | Decision |
| --- | --- |
| Experiment | ONE new run `v2-m3-long-D2-20261024-r1`, experiment phase `long_D2`, evaluation stage `D2`. Not a continuation, resume, retry or relabel of `v2-m3-D2-20261024-r1`. |
| Budget | Absolute 7,200 s from supervisor launch monotonic `T0`. All normal work (verification, entry control, training, evaluation, final checkpoint, worker result, supervisor manifest and terminal receipt) must finish before `T0+7200`. A separate ≤10 s owned-group cleanup is allowed after the deadline only on failure. |
| Parent | Only `learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt`, SHA `ce9c03c8…0544f`, through the exact `M3_implementation.D1.parent_terminal_receipt` anchor. |
| Learner | Byte-identical D2 learner fields of `D2-config.json` (SHA `2d8eb562…7fe3`). Only budget, run seed, experiment identity and the long schedule differ. |
| Run seed | **`5562873868232098305` (`0x4d334c4f4e470201`, ASCII `"M3LONG"‖0x02‖0x01`).** The parent proposal's `5562881586070242563` is `0x4d33535441474503` = `"M3STAGE"‖0x03`, the registered **D3** run seed. Reusing it would collide with the D3 namespace row. Change it before registration. |
| Stop | Immediately when the unchanged D2 progress gate passes on a cadence evaluation (`progress_passed("D2", …)`: mean score ≥ 50 and mean alive frames ≥ 3,060, deterministic argmax, 64 D seeds, cap 18,000). Otherwise stop at the last 16-update block that fits the admission rule. Also stop on nonfinite, KL safety stop, resource, identity, lease, cancellation or entry-control failure. |
| Futility | None. No performance-based early stop. The experiment measures the curve; a futility rule would bias it. Only the existing safety stops apply. |
| Exit codes | `0` = complete and D2 gate passed. `2` = complete and budget closed below gate. `1` = failed. Budget closure is never `passed`. |
| Eligibility | Every artifact of this run is training-parent ineligible under the old contract by construction. A gate pass makes one checkpoint a *candidate for separate parent audit* only. No automatic D3, B, E or student work. |

## 2. Old 1800 s contract versus new 7200 s scope

| | Old registered D2 (`teacher_execution_protocol_v1`) | New long D2 |
| --- | --- | --- |
| Authority | `docs/v2-m3-run-protocol.json` row D2, lease kind `M3_teacher` | New parent protocol + lease kind `M3_long_D2_experiment` |
| Budget | 1,800 s, consumed (1,800.439 s, failed wall guard) | 7,200 s, own single-use row; old D2 budget stays consumed and is not reclaimed |
| Cutoff | `supervision.CUTOFF` 2026-10-24T13:00Z + 600 s receipt reserve | No overnight cutoff; absolute `T0+7200` deadline |
| Run seed | `5562881586070242562` | `5562873868232098305` |
| Validator | `identity.validate_config`, `ckpt.validate_transition` | New controller's `validate_long_config`; the legacy validators stay unchanged and are called only to prove the old D1→D2 contract |
| Stage loop | `Experiment.stage()`: no reserve; dies at wall guard mid-update | Block admission with explicit reserves; normal closure at an evaluated boundary |
| Tags | `candidate`, `periodic` | `long_evaluated`, `long_periodic`, `long_closure_unevaluated`; failure tags `interrupted_mid_update`/`timeout`/`failure` unchanged |
| Receipts | `run-result.json`, `worker-result.json`, `registered-config.json`, `.evaluation.json` | `long-run-result.json`, `long-worker-result.json`, `long-config.json`, `long-identity.json`, `.long-evaluation.json`, `finalization-result.json` (terminal authority) |

## 3. Budget justification from measured D2 timing

Source: `milestone3-D2-curriculum-r1/training-metrics.jsonl`, `launch-command.json`, `run-result.json`
and the seven D2 `.evaluation.json` files (parsed as JSON only).

- Launch `12:14:25.179Z`; first update complete `12:14:45.964Z` (20.8 s: startup, entry eval 2.321 s, update 1).
- Updates 1→104: 1,768.72 s over 103 intervals. Mean **17.172 s**, median 16.913, p90 17.139, min 13.446, max 25.371. Intervals include six evaluations and periodic checkpoints.
- Kill: mid-update 105, 10.9 s after update 104, at 1,800.439 s.
- Evaluation wall fits `t ≈ 3.0 ms × longest-episode decisions + 0.27–0.33 ms × total decisions` (D1 at fixed 500 batches: 5.777 s→9.770 s for 15,886→30,685 decisions; D2 phase-96: 874 batches, 18,422 decisions, 8.185 s). An all-capped D2 evaluation (4,500 batches, 288,000 decisions) projects to ≈92–110 s. Near the gate (mean alive ≈3,060) it projects to ≈20–35 s.
- Each update is 64 env × 256 decisions = 16,384 transitions, 4 epochs × 32 minibatches = 128 Adam steps unless KL stops early.

Projection (not a promise, not a gate forecast): at the measured rate a 16-update block plus its evaluation costs ≈285–310 s. The admission rule below admits about 21–23 blocks, **≈336–368 complete updates (≈43k–47k Adam steps)**, against the old 104 updates / 13,248 complete Adam steps. Roughly 3.2–3.5× the old measured range. Opus's earlier 4.9 h gate projection was an unvalidated linear stochastic-to-deterministic extrapolation. It sets no budget or expectation here.

## 4. Schedule, reserves and stop rules

Clock: `T0` = supervisor launch monotonic (captured at import, as in the r3 reference).
`deadline = T0 + 7200`. `worker_deadline = deadline − 60` (supervisor finalization reserve).
All quantities below use the worker's monotonic clock against `worker_deadline`.

In-run measured bounds (tightening only; floors are fixed):

- `U = max(25.0, 1.25 × max observed complete-update wall)`, where update wall = collection + PPO update + any periodic checkpoint write.
- `E = max(150.0, 3.0 × max observed evaluation wall)`, entry evaluation included.
- `C = 15.0` s per checkpoint write (≈3.95 MB file, fsync).
- `F = 30.0` s worker finalization (checkpoint index, worker result, stream close).

Sequence:

1. Startup verification, parent proof, restore, entry equality checks, environment construction.
2. **Entry (phase update 0).** Require `remaining ≥ C + E + F`. Write `long_evaluated` checkpoint, run the registered entry evaluation, check the exact control (§6). A gate pass here ends the run (it will not; entry is 1.4765625/295.25).
3. **Block admission** at each evaluated boundary `16k`, after a non-passing evaluation: admit the next block iff `remaining ≥ 16·U + E + 2·C + F`. Otherwise close: the final checkpoint is the evaluation checkpoint just evaluated. Outcome `budget_closed_below_gate`, exit 2.
4. **Inside an admitted block,** before update `j` (1-based within block): require `remaining ≥ (17 − j)·U + E + c_j·C + F`, where `c_j` counts the checkpoints still due in the block. If false (unexpected slowdown), stop at the current complete update. Write `long_closure_unevaluated`. Run no evaluation. Outcome `budget_closed_below_gate` with `final_checkpoint_evaluated=false`, exit 2.
5. At `phase_updates % 8 == 0 and % 16 != 0`: write `long_periodic`.
6. At `phase_updates % 16 == 0`: require `remaining ≥ C + E + F`, else treat as step 4. Write `long_evaluated`, evaluate, write `<ckpt>.long-evaluation.json`. If `progress_passed("D2", …)`, stop. Outcome `D2_progress_gate_passed`, exit 0.
7. Safety stops reuse existing semantics exactly: nonfinite losses/gradients/logits (ppo/dev_eval raise), approx KL > 0.1 on three consecutive updates (`GuardStop`), entropy < 0.3 before D1 competence (inert: the D1 parent context sets competence true, as in old D2). These produce a `failed` experiment with preserved checkpoints.
8. If the guard deadline fires anyway (worker deadline reached mid-update or mid-evaluation), write `interrupted_mid_update` (if `progress.in_update`) or `timeout` with exact `update_progress`, inside the 60 s supervisor reserve. Outcome failed, exit 1. If the worker hangs, the supervisor kills the owned group at `deadline`. Cleanup is ≤10 s; a partial checkpoint may then be missing, and the receipt says so.

No evaluation occurs off the registered cadence. No update starts that cannot reach its block's evaluation under the bounds. This tightens the old rule, which had no reserve. With the floors binding, the block admission threshold is 610 s of worker time, 670 s before the absolute deadline. Expected unused tail ≈ 300–600 s. That is the deliberate price of never evaluating off-cadence.

Gate semantics: only a complete deterministic cadence evaluation can pass. A closure checkpoint never receives a gate claim. Budget exhaustion is never competence.

## 5. Identity, lineage and source verification

**Placement.** Controller and tests live outside `python/dodge_rl`, `python/tests` and `crates`, e.g. `learning/runs/v2/postovernight-long-D2-prepare-r1/{long_d2.py,test_long_d2.py}`. `identity.source_inventory` walks those roots: a new file there would change the 75-input inventory and fail every legacy check. Execute inside a read-only capsule. Mirror the r3 construction with manifest version `long_d2_capsule_v1`.

**Step A — legacy proofs, unchanged functions, old contract only.**

1. `identity.check_frozen(D2-frozen-identity.json, 56dcf1ba…bc14f, D2-config)` proves the current 75 sources, foundation, `_native` extension, binary receipts, interpreter, Torch/NumPy, platform, architecture, PPO description, reward/observation/seed versions equal the registered D2 identity. Any OS/Python/Torch drift fails closed. The parent must not relax this.
2. `checkpoints.validate_transition(D1 checkpoint, <D2 frozen identity object>, terminal_anchor=<exact D1 anchor>)`. It proves the D1 terminal receipt, artifact manifest, `candidate` tag, complete update, D1 gate certificate (12.109375/1917.53125), identity equality and the registered D1→D2 transition under the old 1,800 s row. It authorizes nothing about 7,200 s. It returns `(parent_state, certificate)` from `load_checkpoint(…, expected_sha256)`.
3. Also pin and recheck the D1 audit `b0816410…3c08` and execution result by hash.

**Step B — new authorization.** `validate_long_config(long_config, d2_config)`. It requires the exact key set (unknown or missing fails). It requires `strip(long) == strip(d2)` for all learner/environment/device fields. Allowed differences: `version`, `phase`, `phase_settings`, plus long-only `evaluation_stage`, `base_config_sha256`, `long_settings`, each with exact pinned values. Run seed must differ from every registered run and initialization seed.

**Long identity** (`teacher_long_D2_identity_v1`), frozen by the parent with the controller's `freeze` subcommand:
`{version, config: long_config, config_sha256, base_registered_identity_sha256: 56dcf1ba…, base_registered_identity: <exact D2 frozen identity>, parent_checkpoint_sha256, parent_terminal_receipt, protocol_sha256, controller_sources: {long_d2.py, test_long_d2.py: sha}}`.
Checkpoints embed it through unchanged `make_state`, which needs only `config.batch_size`. The controller code is part of run identity, not hidden.

**Checkpoint coupling.** The container stays `teacher_checkpoint_v1` with `resume_mode=fresh_env`, so the unchanged `make_state`/`save_checkpoint`/`load_checkpoint`/`require_complete_update`/`restore_learner` apply. Old training readers still reject long artifacts at several independent points:
(a) the `long_*` tags are not `candidate`;
(b) the files `run-result.json`/`registered-config.json`/`.evaluation.json` are absent;
(c) `validate_config` rejects `phase=long_D2`/version/budget;
(d) the protocol table has no `long_D2` phase or transition;
(e) `assert_lease` requires kind `M3_teacher`;
(f) same-phase resume stays disabled in `remaining_phase_budget`.
`load_checkpoint` can still read the files for later separately registered diagnostics. That is intended. Reading is not eligibility.

**Lease** (`state.active_long_campaign`, exact key set, unknown key fails): `kind=M3_long_D2_experiment`, `authorization=postovernight_user_go_long_D2_7200s_r1`, `run_id`, `protocol_sha256`, `controller_sha256`, `capsule_manifest_sha256`, `capsule_path`, `config_sha256`, `identity_sha256`, `parent_checkpoint_sha256`, `parent_terminal_receipt` (8 exact fields), `budget_seconds=7200`, `cleanup_reserve_seconds=10`, `output`, `cancel_requested=false`. The supervisor checks it before spawn and the worker checks it at every guard sample. A change stops the run. `cancel_requested=true` latches cancellation. The legacy `train_teacher` refuses to run while this lease is active.

## 6. Entry restore and matched lineage control

Order:
1. `seed_initialization(0)`, as the old D2 worker did.
2. Construct the model and Adam.
3. `restore_learner(parent_state)`.
4. **Equality receipt before any environment:**
   - every `model.state_dict()` tensor equals `parent_state["model"]` (`torch.equal`, dtype/shape);
   - `optimizer.state_dict()` equals the parent: state tensors bitwise, `param_groups` exact (lr 3e-4, eps 1e-5);
   - `capture_rng("mps")` equals `parent_state["rng"]` for python, numpy global, torch CPU and torch MPS bytes.
   Record SHA256 of the canonical tensor bytes.
5. Emit the parent's `abandoned_episodes` with reason `long_D2_namespace_transition`. Do not replay them.
6. Build the environment from `training_env_config(<registered D2 config>, [0]*64)` with only `run_seed` replaced; assert that single difference. Then `verify_training_env(env, long_config, [0]*64)` unchanged. That proves the B/D/E exclusions, seed stream/exclusion versions, slot identities, zero episode indices, startup 13 and no reserved seed constructed.
7. Capture the RNG, write the entry `long_evaluated` checkpoint, run `dev_eval.evaluate(model, "D2", "mps", …)`, then capture the RNG again. Require equality (no draw). Require weights unchanged.
8. **Exact control:** the 64 rows equal the old D2 entry rows in `milestone3-D2-curriculum-r1/checkpoint-000010-candidate.pt.evaluation.json` (SHA `d52919c5…b0cc`), field-for-field. Expected means are 1.4765625/295.25. Read this JSON only; never load the failed-run checkpoint. A mismatch is a pre-gradient failure (exit 1, zero updates). The action-mode diagnostic reproduced this control exactly today.

This entry evaluation is the registered `at_entry` cadence point, not an extra evaluation. Training sampling then starts from exactly the carried D1 RNG, as old D2 did. The environment seed namespace differs, so trajectories are an independent replicate rather than a replay.

**Counters.** Carry the parent counters (`updates=48`, `optimizer_steps=6144`, `environment_decisions=786432`, `raw_frames=3139552`, `checkpoint_index=9`) and set `phase_updates=0`. Receipts report `inherited` and `phase = cumulative − inherited` separately. The failed D2 run's 104 updates are not in this lineage.

## 7. Supervisor, worker and finalization

Copy the r3 runner patterns into the new controller. Do not import or edit that frozen artifact.

- `DiagnosticGuard`-style supervisor thread: lease, cancel and file pins every ≤0.5 s; external worker RSS every ≤0.5 s; latched failures.
- Worker cooperative guard: same callback sites as the old `Guard` (collection steps, minibatches, evaluation steps). On the main thread, sample RSS, self-peak and `torch.mps.driver_allocated_memory()` every ≤0.5 s, with the lease every ≤0.5 s and full pins at every update/evaluation boundary and at least every 5 s. Limits: RSS 6 GiB, MPS 6 GiB, separate and not additive.
- Signals blocked across `Popen` and PID assignment. New session; owned PGID = PID.
- `stop_owned` with positive group-absence proof (EPERM fallback to `ps -axo pgid=`), bounded at 9.5 s.
- Publication: `long-run-result.json` → nonrecursive artifact manifest → `finalization-result.json`, with a deadline check after every write.

Do not regress the three repaired r3 defects:

1. **Late false complete:** a deadline crossed during publication revokes the manifest and terminal receipt, then writes a failure receipt.
2. **Unstable manifest:** no artifact hashing unless the owned leader is reaped and the group is positively empty.
3. **Deferred cancel:** cancellation requests counted during cleanup still invalidate completion after the signal context exits.

Training is never restarted, retried or resumed. The output directory is created once with `exist_ok=False`.

## 8. Outcome vocabulary (all receipts)

- `experiment_status`: `complete` or `failed`.
- `outcome`: `D2_progress_gate_passed`, `budget_closed_below_gate`, `safety_stop`, `entry_control_mismatch`, `identity_or_lease_failure`, `resource_stop`, `cancelled`, `wall_guard` or `publication_failure`.
- `progression_gate_passed`: true only for a passing cadence evaluation.
- `teacher_qualified`: always false. B is not opened; qualification needs D3 plus B (`teacher-qualification-v2.json`).
- `training_parent_eligible`: always false for every checkpoint of this run.
- `D3_parent_candidate_pending_separate_parent_audit`: true only for the gate-passing checkpoint. Any D3 needs a new protocol, controller path and authorization, because the old `validate_transition` rejects this run by construction.
- `checkpoint-index.json`: every checkpoint with tag, phase/cumulative updates, `complete_update`, `evaluated`, gate result and `training_parent_eligible: false`.

## 9. Tests and negative controls (Codex, synthetic, no training)

Use fake clocks, fake environments, tiny fake models and JSON fixtures. Any real D1/D2 files are read-only.

1. Config: equality with D2 learner fields. Field mutations fail: each PPO value, device, threads, caps, K, rollout, batch, budget 7199/7201, extra key, missing key. A run seed equal to each registered run seed (incl. D3 `…563`) or initialization seed is rejected.
2. Lease: exact set. Extra or missing key, kind `M3_teacher`, wrong hash, changed anchor field, `cancel_requested` mid-run.
3. Parent: anchor field mutations rejected. Failed D2 run dir/checkpoints (`000022`, `000023`, `000024`) as parent rejected through `validate_terminal_receipt` (status failed) before any Torch load.
4. Old readers reject long artifacts: synthetic long run dir through `validate_terminal_receipt`/`validate_transition`, `default_config("long_D2")`, `assert_lease` on the long lease.
5. Schedule with a fake clock:
   - admission boundary exactly at `16U+E+2C+F` (≥ admits, < closes);
   - closure lands on the evaluated checkpoint;
   - mid-block slowdown produces `long_closure_unevaluated` with no evaluation;
   - deadline mid-update produces `interrupted_mid_update` with progress;
   - no evaluation starts when `C+E+F` does not fit;
   - gate pass at 16k stops immediately with exit 0;
   - budget closure gives exit 2 and never `passed`;
   - `U`/`E` only grow.
6. Entry: a single-element weight, Adam moment or RNG-byte perturbation is detected. A fake evaluation that draws RNG is detected. A one-field row mismatch fails before `collect_rollout` is called.
7. Environment kwargs: equal `training_env_config(D2)` except `run_seed`. `verify_training_env` passes with a fake env and fails on a reserved seed or a wrong namespace.
8. Counters: inherited/phase split. Failed D2 counts are absent.
9. Nonfinite, KL×3 and RSS/MPS > 6 GiB (fake probes) each stop with the correct tag and outcome.
10. Finalization: port the r3 `test_finalization` cases for the three repaired defects, plus a cancel latch during cleanup and a group still present.
11. Protected inventory: before and after equality of the 75 sources, D1/D2 run dirs, r3 runner and state (except the parent's own edits).

Negative controls: each discriminating test must fail against a deliberately broken copy. Examples: admission disabled; tag `candidate`; an off-cadence final evaluation; no RNG equality check; the r3 defects reintroduced.

## 10. Freeze, review, execution and result audit checklist

1. Parent registers the protocol (with the corrected run seed), builds `long-config.json`, freezes `long-identity.json` and seals the capsule.
2. Frozen read-only adversarial review of the capsule against §§4–9.
3. Parent writes the exact lease and launches once.

The result audit verifies:
- terminal receipt and manifest bindings;
- exit code against outcome;
- observed wall ≤ 7,200 s, plus cleanup ≤10 s only on failure;
- owned PIDs absent;
- entry equality and exact control;
- fresh u32 seeds outside B/D/E, recomputed from the logged infos;
- every completed episode's reward identities;
- per-update finite metrics;
- counters inherited/phase;
- every evaluation recomputed from its rows (`validate_summary`);
- the gate decision recomputed;
- checkpoint index tags and ineligibility;
- maximum RSS/MPS;
- protected inputs unchanged;
- no B/E/D3/student, no retry.

## 11. Risks and unverified until the real run

- MPS driver memory over 2 h. Old max 2.456 GB in 30 min. Growth is unmeasured. The guard stops at 6 GiB, preserving checkpoints.
- Thermal or throughput drift, and evaluation-time growth as episodes lengthen. Bounds adapt upward only. A large slowdown closes earlier.
- The learning curve beyond 104 updates is unknown. A gate pass is not predicted. Plateau or collapse are both possible.
- Entry control determinism on the current OS/MPS state. The action-mode diagnostic matched today, but the risk is not zero. A mismatch fails before training.
- The environment platform string must still equal the D2 freeze (`macOS-27.0.1-arm64`). A drift blocks the run.
- The cooperative MPS guard cannot sample during a blocked native or MPS call. The supervisor wall and RSS still apply.
- Disk ≈250 MB (≈46 checkpoints × 3.95 MB plus logs).
- The proposal run seed collides with D3. It must be corrected.

## 12. Alternatives considered

- **Per-update admission with an off-cadence final evaluation.** Uses ≈5% more budget but adds an unregistered evaluation opportunity. Rejected.
- **Extend or relabel old D2, or reuse a failed D2 checkpoint.** Forbidden.
- **Editing `validate_config`, `Guard` or `CUTOFF`.** Breaks the 75 pins and the old contract. Rejected.
- **A new checkpoint container version.** Stronger rejection, but forces rewriting the save/load/restore utilities and blocks later diagnostics. Rejected in favor of the layered coupling in §5.
- **Futility stop or entropy/hyperparameter change.** Not justified by the action-mode evidence. Rejected.
