# Frozen RNG probe R4 review

**Result: BLOCKED — one P2 finding.** Source-only review; no launch or qualification authority.

Exact registration SHA-256 `34b35307a9559ca2a7f74f0ca4567c3d30590af4e285b6295e21bbc8ae898895` and authoritative manifest SHA-256 `8b31a2598dd849c6d89ad817092bdc2d64c33da6fa588dad80ce699ef7f5a555` match. All manifest members, registered input pins, and parent replay source copies match. Current R3/R4 buffers reproduce the supplied diff. Full hashes are in [receipt.json](receipt.json).

Paths below abbreviate `learning/runs/v2/confirmed324-probe-signal-postflight-repair-sol-20261026-r4/` as `R4/`.

## Blocker

**R1 / P2 — first signal during receipt publication leaves stale pending acceptance.** `R4/supervisor_cli.py:161–168,239–244,8–13`. Reachable trigger: worker exits 0; all 19 checks and inventory pass; line 239 constructs the successful result; the first SIGTERM/SIGHUP/SIGINT arrives before `exclusive_json` serializes it, such as during its parent-directory `mkdir`. Deferral keeps finalization running. The handler updates nonlocal `reason`, but the already-built result retains `stop_reason=null` and `status=accepted_pending_parent_postflight`. A complete receipt can record that verdict and a handled signal, then line 244 raises a supervisor failure. A signal after serialization can also be missing from persisted signal history. This is a receipt/outcome inconsistency, not a live-worker cleanup failure or the disclosed partial-JSON limitation.

The signal control injects its first interrupt during monitoring (`test_failure_controls.py:80–94`); finalization injection at lines 146–147 occurs only after failure is already established. It does not cover this otherwise successful late-first-signal path. Bind finalization's signal policy, persisted verdict and terminal outcome consistently, with a focused control. Finding is static; no reproduction was executed.

## F1–F5 disposition

- **F1:** Original repeated-interrupt cleanup defect closed: claim/spawn deferral, permanent deferral on first interrupt, and protected cleanup/postflight/fsync (`supervisor_cli.py:158–243`). R1 remains a separate finalization regression.
- **F2:** Closed: ownership callback runs immediately after exclusive creation; creation and write completion are separate (`supervisor_cli.py:8–15,169–180,232–240`). Partial marker writes/fsync faults retain a failure receipt; preexisting markers stay unclaimed.
- **F3:** Closed: repeated worker cache checks and required outer cache postflight (`worker_cli.py:23–25,89–110`; `supervisor_cli.py:68–70,137`).
- **F4:** Closed: 19 independently guarded checks run on every claimed exit, including cleanup-source bytes; failed/unavailable checks and inventory errors prevent pending acceptance (`supervisor_cli.py:115–155,217–240`).
- **F5:** Closed: same-buffer hash/parse, exact three-replica inventory, all six seed fields, parent/backend/Torch bindings, and aggregate runtime/scope/row equivalence (`supervisor_cli.py:77–114`).

## Contract and evidence limits

`execute()` calls preflight before claim. Exact lease, conflicting leases, marker/cancel/cache/output conditions, source/interpreter/input pins, and fixed limits remain enforced. Worker starts a new session; imported cleanup forwards TERM/KILL with bounded polling/reap. Raw child exit and independently sampled process-group absence gate the result. CPU seeding precedes explicit MPS seeding; exactly three initial state pairs bind the complete vectors. No model/environment/training or checkpoint deserialization appears in this probe flow. Worker asserts actual prefix and unresolved venv invocation and forces final separate RSS/MPS sampling.

Parent log reports 33 passing synthetic controls; its copied source bytes match R4. Retained receipts support repeated signals with raw `-9`/group absence, claim faults, cache changes, missing pins, malformed heartbeat, and inventory failure. Consumer controls exercise valid-hash substitutions. These are inspected artifacts, not tests rerun here or actual MPS proof.

Limits remain work 45s, outer 55s, cleanup 10s, startup 12s, poll 0.2s, stale 2s; RSS and MPS caps are separately 6442450944 bytes. No hard watchdog covers blocking filesystem/hash/fsync/finalization; imports precede first MPS heartbeat; exclusive final writes can be partial; package bytes are unpinned; `runtime_root` remains metadata. These disclosed limits are not additional blockers.

Observed four lease fields null, registered cache empty, marker/cancel/output absent. Exact lease is not installed: current preflight would reject before claim. No process inspection, tests, target imports, runtime calls, launch, lease/marker changes, or repairs occurred. Only this review directory was written.
