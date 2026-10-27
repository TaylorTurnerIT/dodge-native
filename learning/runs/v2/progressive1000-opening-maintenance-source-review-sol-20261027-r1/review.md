# Independent source review

Result: no blocking defect found in the revised curriculum implementation or candidate configuration bindings. One P1 integration blocker affects the two unlaunched baseline controls. This review grants no launch authority.

## Finding

**P1 — Existing baseline runtime fails exact-member validation.** `learning/runs/v2/progressive1000-throughput-runtime-parent-20261027-r2/contracts.py:124-125` rejects any runtime file outside its manifest; `contracts.py:166` enables that exact check. The runtime currently contains unmanifested `runtime/dodge_rl/models/__pycache__/teacher.cpython-312.pyc` (13,188 bytes; SHA256 `9e752090856f1a41e6982d7bb6a898df10eeb5dbc570316b3ed1b6275206bf86`). Candidate index lines 14 and 21 retain control replicas 2 and 3 on this runtime. Trigger: attempt either registered control after other gates pass. Consequence: preflight raises `runtime member set drift`, preventing completion of the three-pair comparison. Parent must reconcile this drift and review resulting bindings before those launches. Preserve the observed artifact; this reviewer changed nothing. This finding does not establish a defect in completed control 1 or invalidate its historical receipt.

## Verified source behavior

Paths below are relative to `learning/runs/v2/progressive1000-opening-maintenance-runtime-parent-20261027-r1/`.

- `runtime/dodge_rl/scheduler_reference.py:37-52,93-101`: deterministic, RNG-free permutation of 70 current-H and 30 full-18000 assignments per completed 100-assignment block, including generation 0. Partial blocks need not be 70/30. Generations advance H by 1000; generation 17 has 100 identical 18000 horizons.
- `runtime/dodge_rl/curriculum.py:124-130,148-163,173-182,242-277`: normal starts, persistent per-episode assignments, no forced resets at promotion, and native practice cutoff only for alive H<18000 slots. Full-game slots continue beyond early H. True death and ordinary cap take precedence; cutoff preservation checks retain reward and final observations.
- `runtime/dodge_rl/ppo.py:165-170,234-249,343-372`: unchanged reward identity and scaling; final observation valued before reset; truncation bootstraps while stopping GAE carry; death disables bootstrap. No new reference KL, BC, or critic freezing.
- `runtime/dodge_rl/scheduler_reference.py:117-150`: full-game completions are accepted but excluded from shorter-H mastery by both generation and horizon. Old in-flight generations remain excluded. Mastery advances only after complete PPO updates. The unchanged 10-update minimum and 60-update budget permit at most six promotions; reaching 18000 is not promised.
- `runtime/dodge_rl/curriculum.py:279-308,363-388` and `worker.py:131-169`: assignment/completion records, interval and update exposure, in-flight state, and startup/reset costs retain realized exposure. Episode proportions do not imply frame or decision proportions; full-game episodes can die before later exposure.

## Hashes, binding, and baseline interpretation

Recomputed source SHA256 `51aa867e43b3a047f057ef07069c9939615d4a1db2939e484d0f974cac87b85e`, runtime SHA256 `84e730ee638344460fe9bda693bc986879c39621fa7ef99ba35afd50b0f78b69`, and baseline source SHA256 `e14147338e8da864b1e51c1928124b5103700e22c3ae389e5642bf92c6561f0a`. Every listed source/runtime member matches; the successor runtime has no extra files. Only `scheduler_reference.py` differs among the 12 runtime members. Driver checkpoint/identity paths are correctly rebased with unchanged definition hashes.

All three candidate hashes match the index. Each binds the new source/runtime, exact package configuration, matching parent/PPO/schedule/vector/reference/exclusions, and distinct ownership paths. Their only differences from corresponding old controls are arm/enablement, declared ownership, source/runtime identity, and `shared_config.curriculum_assignment_policy`. Candidate caches exist empty; outputs, claims, and launch markers are absent. No additional candidate integration defect found.

Completed control 1 can scientifically serve the descriptive baseline **conditionally**: parent must explicitly accept the cross-source normalization above and unchanged learner settings. `successor_identity.py:21-28` rejects these cross-source registrations and does not supply that acceptance. `control-equivalence.json` reports 109 passing CPU checks; source inspection confirms the equivalence test compares one 64x256 rollout/PPO update using `FakeEnv`, `TinyNet`, and fresh Adam (`tests/test_maintenance.py:59-90`). This supports the unchanged disabled collector path, not accepted-transformer/MPS parity or 60-update equivalence. Static identity of the actual learner/native bytes supplies separate evidence.

## Limits and remaining gates

Source/AST/hash/JSON review only; 41 Python files parsed. No project/Torch/native imports, checkpoint deserialization, tests, games, training, qualification-content inspection, agents, or external writes. CPU successes and control-1 terminal audit are supplied evidence, not rerun here. No performance or learning changes proposed. Parent comparison acceptance, exact source acceptance, supervisor-r3 successor worker/source binding, and fresh parent gates remain pending; candidate status and this review do not authorize launch, evaluation, selection, or promotion.
