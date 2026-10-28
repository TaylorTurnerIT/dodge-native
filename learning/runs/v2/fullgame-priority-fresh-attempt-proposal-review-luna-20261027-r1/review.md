# Fresh uniform attempt proposal review

**Ready for user authorization; no blocking preparation findings. Launch authority remains absent.** The proposal preserves the failed attempt and prepares one new uniform registration with fresh output, claim, marker, cache, and lease paths.

## Review evidence

- Proposal SHA-256: `a6156053928fcd431e8f3406846be66598bb00313cb8daa5e58da12464c00737`. One-run index SHA-256: `adf4d0cd8038f4f2b61c870931e71451f4119614eaf462b6527bdf10727a6684`. Uniform registration SHA-256: `015464219f2da1f6f69867c94558d5b406f82ee70b7dffa1a38d3c9ab9c820fa`.
- Registration binds r3 source manifest `a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2` and unchanged runtime manifest `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`. It retains the old pool, vector, RNG reference, parent checkpoint/receipt, priority probabilities, PPO schedule, and resource limits. Changed fields bind the r3 source/runtime paths, fresh capsule paths, and a new expected lease owner token.
- R3 fixes the prior failure at its source. `driver_binding.py:15-20` derives checkpoint and identity pins from its own package path and keeps the accepted byte hashes. `runtime_adapter.py:91-99` imports checkpoint code from registered `runtime_root`. `driver_binding.py:87-98` still checks file hashes, exact loaded origin, and function code identity.
- New output, attempt-claim, launch-marker, dispatch, and parent-gates paths are absent. Registered cache exists empty. Old launch marker and failed worker result remain present; old attempt claim remains absent. The incident audit records `failed_pre_environment_attempt_preserved_not_comparison_eligible` for the old registration hash.
- `fresh-attempt-proposal.json` says `awaiting_fresh_user_authorization_no_launch`; the index says `launch_authority: false`; `parent-gates-proposal.json` says `pending_fresh_retry_authorization`. Actual `parent-gates.json` is absent. `start_one.py:35-37` requires and hashes that missing file, so this packet cannot dispatch as reviewed.
- Wrapper differs from reviewed r2 parent wrapper only in source package path, generic index filename, and run-local dispatch path. It still selects one indexed run ID, checks unspent paths and dependency pins, binds source acceptance separately, launches one observer, and contains no retry or automatic audit/promotion path.

## Limits

This is a hash, JSON, and source review only; no live preflight or launch occurred. No lease/state, marker, claim, or package input changed. No Torch, MPS, native, model, or checkpoint load occurred. Actual new-profile MPS training has not yet been demonstrated; the fresh authorized attempt would establish it. User authorization and parent gate creation remain separate required steps.
