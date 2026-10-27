# Expanded evaluation registration proposal

Status: proposal only. No launch, gate, lease, checkpoint, ledger, shared-state, or implementation authority. Current incumbent remains update 324. Current 64-seed evidence remains unchanged. Finalizer source review for update 348 remains pending.

## Evidence set

Rejudge accepted updates 180, 204, 276, 300, 324, and 348 on one frozen ranking cohort of 1,024 seeds. Keep selection evidence distinct from independent confirmation. Use identical deterministic action mode, cap 18,000 raw frames, D2 raw-frame accounting, death accounting, and conservation checks. Report mean, paired standard error and confidence interval, per-seed IDs and outcomes, plus Q1/Q4 group means for each quarter of the 1,024 seeds; do not call these quantiles. Rank on the prespecified cohort summary; do not silently change metrics or cohort after seeing outcomes.

Before confirmation opens, freeze and hash the selected checkpoint and selection record. Then evaluate that one checkpoint once on a disjoint 1,024-seed confirmation manifest, paired against incumbent 324 on identical seed assignments. No next-best substitution, retry after failure, or future reuse of this confirmation cohort. One confirmation still leaves sequential future-confirm type-I uncertainty; later claims require a new prospectively reserved confirm block and an explicit sequential-testing policy. Selection maximum and integrity-retention statistics are development evidence; only the untouched confirmation estimates independent generalization.

Current fixed/linear 324→384 comparison used the same master seed 4200000001 for one matched pair. Preserve that fact; do not apply any claim that every run used a fresh seed to this pair. One pair cannot establish an LR causal effect. Endpoint linear 384 was worse; no causal LR benefit is established.

## Seed governance

Create explicit immutable seed manifests for ranking and confirmation, each with 1,024 unique IDs. Reserve prospective disjoint ranges before any run. Exclude known B/E/D128 ranges and past training exposure. Existing exclusions cover only D128; fresh D addresses are not automatically training-clean. Require a full retrospective training-seed log, ancestry, and in-flight-run audit before launch. Missing proof, collision, overlap, or unknown ancestry fails closed before launch. Do not inspect or open B/E outcome files.

## Cost and capacity

Total planned evaluations: 7,168 candidate episodes (6 × 1,024 ranking + 1 × 1,024 confirmation), plus 1,024 incumbent comparator episodes for confirmation: 8,192 episodes. At cap 18,000, strict maximum is 147,456,000 raw frames, before overhead. This is arithmetic, not a runtime estimate. Before launch, run a permitted throughput benchmark and conservative full-cap projection; reject launch if projected wall/resource budget exceeds a separately allocated evaluation budget. Evaluation budget and wall accounting stay separate from training budget.

For future training comparisons, prospectively reserve at least two, preferably three, independent training seeds per arm. Use same accepted parent, same seed assignments across arms, equal update counts and fixed endpoints. Report fixed endpoint separately from operational-best selection. No current data prove LR causality.

## Parallel preparation and review

Prepare manifests, immutable candidate receipts, evaluator contract, seed audit, cost projection, and review in parallel under separate owned outputs. Each preparation/review records source pins and hashes. Reconcile all findings before any separate one-use confirmation authorization. Advisory does not change gates, leases, registration, incumbent, or launch state.

For any later concurrent campaign proposal, replace one shared lease with a parent-owned lock/CAS registry: unique run owner, lease, cancellation marker, and output namespace per run. Retain each campaign's 6 GiB RSS and MPS caps; enforce host aggregate headroom and pressure caps. Never bypass frozen guards or clear old leases retroactively.

## Immutable candidate pins

Six checkpoint paths and byte SHA-256 values are recorded in `proposal.json`. Values not recoverable from accepted parent receipts/audits are explicitly pending and block registration. No checkpoint binary was opened or loaded for this proposal. Preserve predecessor sources, root README, state, checkpoints, and ledgers.
