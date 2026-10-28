# Full-game seed-priority experiment

This package prepares the first authorized follow-up experiment: uniform seed sampling versus capped opening-hard sampling from one frozen training-only pool. Both arms use normal-start, uncropped full-game episodes and collect new PPO transitions from their current policies. Reward, model, optimizer lineage, LR, update budget, and environment stay fixed.

The native explicit-seed-list constructor reports `seed_mode.mode="evaluation"` and `seed.evaluation=true`. This package preserves those native fields verbatim. Its new `explicit_seeded_training_v1` adapter accepts a seed only when it matches the parent-audited training-only pool. That is a changed Python collector/runtime identity and needs independent source review. It does not turn evaluation metadata into training metadata.

`seed_priority.py` defines the frozen pool contract and paired deterministic streams. The treatment uses a 50% uniform floor and 50% opening-hard component. With the 512-seed pool split evenly, hard-seed inclusion probability is 1.5 times uniform and remains below the proposed 4x cap. Repeated seed visits are intentional sampling with replacement. A fault never triggers a retry or seed substitution.

`seed_vectors.json` contains three proposed six-key vectors for the new study ID. They are not reserved, probed, applied, or launch authority. Parent can measure independent CPU/MPS references with its already-reviewed one-shot probe.

`build_registration.py` refuses to build drafts without a parent registry that accepts pool freshness, history closure, and both D4/D5 reservations. The pool itself is absent until that evidence is supplied. D300 is consumed and excluded.

No training, evaluation, checkpoint load, native constructor, model import, RNG probe, launch marker, lease, or attempt claim was created here. The copied runtime includes the accepted native binary as an input pin; this package did not build or exercise it.

## Synthetic checks

`tests/test_seed_priority.py` checks pool rejection rules, deterministic streams, pool-only membership, paired uniform draws, and the theoretical inclusion cap. It uses synthetic fixtures and imports only the standard library.

## Limits

A full-game episode assignment creates an opportunity to survive later. It does not guarantee exposure to late ages: early deaths still reduce later-age gameplay frames. Report age-binned raw frames and seed assignment counts alongside opening, tail, mean, and death-cause metrics.
