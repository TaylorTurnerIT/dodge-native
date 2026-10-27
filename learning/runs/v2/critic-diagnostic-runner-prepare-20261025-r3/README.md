# Critic diagnostic runner revision 3

Status: ready for frozen Claude Haiku review. This is preparation only. No campaign, environment step, inference evaluation, PPO update, or seed consumption occurred. The consumed r1 registration and every prior failed artifact remain untouched.

The comparator canonicalizes `dict` and `OrderedDict` as mappings. Framed hashes preserve keys, scalar types, tensor dtype/shape/bytes, and list/tuple distinctions. Entry restoration evidence persists model, Adam, and RNG digests plus mismatch paths before the fail-closed decision; it never writes model weights or RNG contents. Existing identity and lineage checks remain unchanged. R2 launcher cancellation and process-group fixes remain intact.

Validation passed: all 15 original contract tests plus one mapping test; actual Torch model/Adam restore fixtures; and a startup-only rehearsal with the original accepted D1 checkpoint and frozen isolated runtime. Reproduce rehearsal explicitly with:

```sh
/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python startup_rehearsal.py
```

The rehearsal restored and matched model, Adam, and RNG before environment creation. It ran in 0.869 seconds; observed peak RSS was 297,975,808 bytes and MPS driver memory was 8,880,128 bytes. Full commands, attempts, hashes, and resource samples are in `implementation-result.json` and `startup-rehearsal-result.json`.

Historical best development cohort remains survival Q1=648.25, Q4=4508.8125, mean=2240 frames. This is reference context only; r3 makes no runtime performance or qualification claim.
