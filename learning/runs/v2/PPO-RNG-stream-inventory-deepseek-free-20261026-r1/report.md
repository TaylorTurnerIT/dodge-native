# RNG stream inventory and proposed Layer B seed vectors

Proposed only. No seed is reserved, no reseed or launch happened, no predecessor was edited.

The pinned runtime has six actual streams. The MPS default generator draws every `Categorical.sample()` action (ppo.py 312). The CPU default generator draws `torch.randperm(16384)` once per epoch (474) and every constructor init (teacher.py 109), which restore discards. Python `random` and NumPy global are captured and restored but never drawn. There is no owned NumPy generator, no dropout mask, and no evaluation RNG (argmax). The environment master seed is a pure SplitMix64 namespace (seed.rs 122-123); each slot's native PICO-8 RNG is rebuilt per episode and never checkpointed. `restore_rng` fails closed on backend mismatch (checkpoints.py 33), pinning Layer B to `torch_global_mps`. A CPU backend would fuse action sampling and shuffling into one generator.

`seed-vectors.json` gives three replicas six fields each, SHA256-domain-separated from the public study ID, identical across arms, distinct across replicas, bounds-checked, and rejecting all reserved and prior master seeds. The env control precomputes 64 actual seeds from the parent episode indices: zero reserved hits, zero zeros, 64 distinct.

Reseed order: verify model/Adam/RNG, reseed, assert model/Adam unchanged, construct environment, apply the 396-origin controller, then train. Adam moments and steps stay intact.

Common random numbers share noise within a pair; they do not make pairs independent. Same policy RNG plus a new env seed varies only environments.

Unresolved: exclusion union, runner seed binding, reseed helper, vector registration, LR logging, runtime first-draw capture. Three descriptive pairs; no .05 claim.
