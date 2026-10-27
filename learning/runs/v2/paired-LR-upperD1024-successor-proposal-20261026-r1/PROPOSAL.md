# Successor proposal: upper-D1024 ranking, separate confirm, ≥2 training replicas, concurrent leases

Status: design proposal only. No seeds generated, no training, no leases, no evaluator edits. The frozen 64-seed r3 evaluator and the current review are not modified.

## Question

Does linear LR (average 2e-5) beat constant LR (3e-5) on paired development seeds, and is any difference robust across training replicas? The current single pair confounds average LR with schedule ordering, so it supports no causal claim about ordering.

## Design

1. **Ranking set, 1024 seeds.** Disjoint from the 64-seed block `0xD0000040..0xD000007F`, from `training_excluded_ranges`, and from every seed used by any training replica. Generate once, freeze with a manifest SHA and a disjointness proof computed against all registered seed sources. Do not claim "prior nonuse proven" unless the history scan supports it.
2. **Confirm set, 1024 seeds.** Disjoint from the ranking set and from all training. Its decision rule (metric, effect threshold, sign test or bootstrap method) is registered before any evaluation runs. Ranking picks nothing for the claim; confirm is the only evidence used for the claim.
3. **Training replicas, ≥2 per arm.** Each replica has its own registered seed, config, and provenance; its endpoint is at the same phase update (384) and cumulative update (432). Replicas must share the native and runtime member map. Decide before running whether ordering is in scope. If yes, add a control arm that matches average LR but not schedule order; if no, state average-LR-only.
4. **Evaluator successor.** Replace hardcoded `SEEDS`, `EXPECTED_MANIFEST_SHA256`, `CONSTANT`, `TRAINING_REGISTRATIONS`, and endpoint pins with a successor registration schema v3 that carries the manifest, endpoint set, and replica set explicitly. Keep the r3 guard, order, immutable-publication, and pin-before-import structure. Apply findings 1–4 from the r3 review before reuse.
5. **Concurrent leases.** Each training replica and each evaluation holds its own lease, its own output directory, and its own registration. No shared mutable state. Publication remains per-path exclusive. Cap concurrency by a registered resource budget (CPU threads, memory, MPS use) and check the budget in the guard callback before each job starts. Lease expiry and cancel paths must release resources without touching other leases.
6. **Resource estimate.** Per evaluation: 1024 episodes at up to 18000 raw frames per arm. Per arm-replica pair: estimate from the 64-seed timing scaled by 16, plus training time per replica. Produce the estimate before requesting approval.

## Risks

- Seed-namespace overlap with training or prior evaluations is the main validity risk. The disjointness proof must cover all registered sources, not only scoped scans.
- Concurrent leases multiply exposure to shared-state bugs. Start with sequential execution and add concurrency only after a lease-isolation test passes.
- More replicas raise training cost; the cost decision belongs to the user.

## Decisions needed from the user before a successor task starts

- Exact replica count (proposal: 2 per arm, or more).
- Whether schedule ordering is in scope (determines if a control arm is needed).
- Confirm-set effect threshold and test method.
- Approval of the resource estimate and concurrency cap.

## Next step

Open a separate successor task with these decisions. Do not start training or lease acquisition from this proposal.
