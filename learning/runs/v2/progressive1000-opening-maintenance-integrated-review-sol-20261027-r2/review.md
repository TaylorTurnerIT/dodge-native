# Final narrow integration review

**Result: no blocking findings in the final integration.** The previous P1 has no reachable trigger through these five replacement registrations. This review grants no launch authority.

Paths below are relative to `learning/runs/v2/`.

## Binding and P1 closure

Recomputed source manifest SHA256 `51aa867e43b3a047f057ef07069c9939615d4a1db2939e484d0f974cac87b85e`, runtime manifest SHA256 `84e730ee638344460fe9bda693bc986879c39621fa7ef99ba35afd50b0f78b69`, and supervisor manifest SHA256 `940c53a8f01a98cb3cb16b2f38222b90cf7c55197f8c537e9baa7f0e6cc4e214`. All 46 source, 12 runtime, and 13 supervisor listed members match. The new runtime has exactly its 12 declared files. The reviewed curriculum source has not changed.

`progressive1000-opening-maintenance-supervisor-parent-20261027-r1/binding.py:15-19` binds that source and retains all limits. Against throughput-supervisor-r3, its only production changes are `SOURCE` and `SOURCE_SHA`; `observe.py`, `terminal.py`, `execute_once.py`, and `dependency-binding.json` are byte-identical. The launcher and audit helpers differ from the monitored-comparison originals only in supervisor path; `watch_progress.py` is byte-identical.

`progressive1000-opening-maintenance-integrated-parent-20261027-r1/registration-index.json:12-46` contains exactly curriculum replicas 1/2/3 and control replicas 2/3. Every indexed registration hash matches; every replacement binds the same clean source/runtime. The old baseline still contains the preserved 13,188-byte `teacher.cpython-312.pyc`, SHA256 `9e752090856f1a41e6982d7bb6a898df10eeb5dbc570316b3ed1b6275206bf86`, matching `PPO-performance-cache-incident-parent-20261027-r1/incident.json`. Its listed runtime members remain unchanged. No cleanup or manifest weakening occurred in this review. Exact-member enforcement remains at the new `contracts.py:122-125,166` and supervisor `binding.py:161-162`; future controls no longer use the contaminated runtime. The incident's reported import cause is documentary evidence, not independently reconstructed here.

## Registrations and comparator

All five replacements preserve their corresponding original parent hashes/fingerprints, PPO, schedule, six-key vector, reference/approval, exclusion union, initial episode indices, runtime versions, and limits. Changes are confined to source/runtime identity, `shared_config.curriculum_assignment_policy`, and fresh owned paths/tokens. Their shared configurations and vectors match the new package JSON exactly. Outputs, claims, markers, and supervisor dispatch paths are absent; caches exist empty. Old corresponding registrations remain unlaunched. No prior attempt or receipt was changed.

Replicas 2/3 match across arms except arm/enablement/run identity and owned paths/tokens. Replica 1 matches the completed control on all learning, budget, parent, and seed fields; its source/runtime and assignment-policy metadata differences are explicitly normalized by `control-baseline-acceptance.json:6-18`. Only `scheduler_reference.py` differs among old/new runtime members. The disabled collector does not instantiate its scheduler. Parent acceptance is descriptive, with no automatic selection or promotion.

The completed control1 registration hash matches the index. Its existing parent audit records 60 updates, 983040 decisions, five embedded checkpoint checks, clean worker/observer exits, absent process groups, and 1697.5800122499932 seconds. Its lease-release receipt authenticates that audit's SHA256. These are retained parent receipts; this review did not rerun their checks or inspect checkpoint contents. Audit time `2026-10-27T15:44:27.402222+00:00` precedes incident-record creation `2026-10-27T15:50:43.709581+00:00`; exact cache-creation timing is supplied incident history.

## Launch, terminal accounting, and remaining gates

The fixed bounds remain work/total/cleanup `3780/3790/10` seconds, RSS/MPS `6442450944` bytes each, raw frames `16712512`, resets `983040`, and retries `0`. The 60×64×256 budget remains 983040 decisions. No training optimization was introduced.

`launch_one_r3.py:35-42,54-73` requires exact registration-specific parent gates and evidence pins, refuses spent ownership paths, checks source/cache/dependencies, binds acceptance/envelope, and spends the launch marker before observer dispatch. Source acceptance and gate acceptance are absent for all five registrations, as expected before parent finalization. The review does not fill them in.

Supervisor `observe.py:194-240,279-313,335-360` retains absolute work/total deadlines, one worker launch, original cleanup/reaping rules, sticky first failure, and bounded/deferred failure accounting. `terminal.py:94-126,130-200,201-214` retains update/optimizer counts, gameplay plus startup/reset frame conservation, scheduler/assignment replay using the new SOURCE, five integrity file hashes, resource limits, and pending-parent status. `audit_one.py:31-47,54-73,100-117` retains parent group/exit checks and embedded-checkpoint audit before exact lease release. That future audit is mandatory; it was not executed here.

## Evidence limits

This review used only source text, AST, hashes, JSON, and standard-library filesystem inspection: 57 Python files parsed and 20 integration/evidence JSON files parsed with duplicate-field/nonfinite rejection. No project/Torch/native imports, checkpoint deserialization, tests, games, training, qualification-content inspection, further agents, ledger/source/lease writes, or performance changes occurred. Only this review directory was written.

The new supervisor's completed receipt reports 11 successful synthetic checks and no subprocess launches. Existing CPU evidence reports 109 successes; the disabled equivalence test uses FakeEnv, TinyNet, fresh Adam, and one 64×256 CPU rollout/PPO update (`tests/test_maintenance.py:59-90`). Neither supports accepted-transformer MPS parity, 60-update equivalence, or qualification. The brief's prior 29 supervisor checks remain supplied historical evidence; this narrow review did not re-establish that aggregate. Byte identity establishes preservation of the previously reviewed production supervisor.

Parent must still finalize exact source acceptance, registration-specific gates and approval, serialized lease/marker handling, and terminal audit for each authorized run. Evaluation, selection, qualification, promotion, and launch remain outside this review's authority. Unchanged curriculum design was not reopened.
