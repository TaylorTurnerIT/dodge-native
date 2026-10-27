# Confirmed324 worker event R3 source review

**No blockers found within R2-01 closure and narrow regression scope. R2-01/P2 is closed in the inspected source.** Parent retains source acceptance and all launch/runtime authority. Locations below refer to `../confirmed324-worker-event-repair-sol-20261026-r3/`.

## Closure and regressions

- `runtime_adapter.py:159–173` calls the worker callback once, unconditionally after successful collection and before observation reassignment, PPO, or diagnostics. Both event lists are deep-copied; callback return is ignored. No catch or retry intercepts callback exceptions.
- `worker.py:120–126` uses the unchanged pinned `ordered_episode_events` (`D2-retained300-continuation-freeze-20261026-r5/runner.py:620–624`): rollout-step order, completed before reset at ties, complete payloads, and `phase_update=324+local`. `emit` serializes before writing and flushes (`worker.py:28–30`); each event is fsynced before callback return. The former post-success event loop is removed, preventing duplicate publication.
- Serialization, writer, flush, fsync, or callback exceptions leave the callback before PPO. No application retry, seek, truncation, or record rewrite is added. A failed/partial record is not promoted to a successfully synced record; a failed fsync proves no crash durability for that record. PPO/diagnostic failures occur after successful journal syncs.
- Counters and candidate eligibility advance only after adapter return and completeness checks (`worker.py:127–143`). Shared result/progress/candidate containers preserve prior accepted progress on failure (`:104–108`); `execute` records failure and invokes adapter cleanup before its result write (`:167–182`). Cleanup drops the environment reference (`runtime_adapter.py:217–219`); actual native release remains unqualified. The spent R5 claim remains untouched.
- Exact diff changes no other runtime/worker behavior. Five R5 implementation copies, contracts, CLI, LR schedule, restore-after-durable-claim order, reseed fingerprints, episode indices, and local12/24/36/48/60 candidate cadence remain unchanged. Disposable constructor bootstrap remains the accepted source boundary.

## Controls and evidence limits

The six controls are concrete: nonempty completed/reset payloads followed by PPO or diagnostic failure; 60 successful collections with 120 event records exactly once; reset-writer failure retaining the first synced record and blocking PPO/candidates; first-event fsync failure blocking PPO/replay; and nested payload mutation plus ignored callback return (`test_events.py:157–220`). Shared assertions check failure counters/progress, no failed-update candidate, one cleanup, and unchanged spent claim (`:128–154`).

Parent receipt/log report all 43 controls passing under project Python 3.12.15 `-B`. I independently matched all 43 log identities to source ASTs and all 27 parent source copies to R3 pins; I did not replay tests. Failure controls use the first update, patched constructor/guard/cleanup, one completed/reset pair, a writer exception before reset emission, and first-event fsync failure. They do not simulate literal partial OS writes, separate serialization/flush faults, later-update failure, process crash, or real native cleanup. Straight-line propagation supports source closure; synthetic evidence proves no real runtime behavior.

Independent read/hash/AST/JSON/diff checks passed: 27 source pins, 34 artifact pins with exact inventory, 58 immutable inputs, 38 predecessor/review pins, 11 authoritative R5 pins, five unchanged R5 copies, 16 Python ASTs, six inert templates, and exact reconstructed R2 diff. Exact hashes and check details are in `receipt.json`.

## Exact identity and authority

- R3 source manifest: `5cb2cdf6bb857473600c7671caa579bb9d49bd3b3bc573ee4c76d635508757ab`.
- Exact R2 diff: `4685cbf67e0dc4f0c4fbf059e2104d9e3287e98267a4aab1b8d40500f1d3d966`.
- Authoritative R5 manifest: `2b0caf00a5d5e765726d080fd5647211190e472d74ffb33b3466e477cb2906a9`.

Only stdlib reads, SHA-256, AST/JSON inspection and diff reconstruction ran under `python3 -B`. No target imports/tests, runtime imports, model/environment execution, checkpoint deserialization, MPS, builds, repairs, delegation, commits or pushes occurred. Only this new review directory was written.

Three exploratory pairs remain constant `3e-5` versus linear `3e-5` to `1e-5` over 60 updates, phase324/cumulative372 through phase384/cumulative432; no formal method claim at n=3, curriculum changes, or selection. Accepted three CPU/MPS initial-state pairs are not restore qualification. Six final registrations, supervision, calibration/resources, real class/backend/accepted-state restoration/readbacks, runtime validation, terminal audit and separate evaluation/selection remain parent-owned open gates.
