# Frozen registration source review

**Result: BLOCKED — 2 P1 and 3 P2 findings. Source review only; no runtime qualification.**

Reviewed R3 supervisor, worker, probe, builder, tests, fingerprint helper, imported cleanup primitives, and the exact parent registration. Paths below abbreviate `learning/runs/v2/confirmed324-probe-venv-source-repair-luna-20261026-r3/` as `R3/`. Full paths and exact SHA-256 inventories are in `receipt.json`.

Registration SHA-256: `e0e94321c17dbfc69cbde7da689bab43f8d7088a9c59cda6f30be9727b58f56b` (matched).

## Blockers

1. **F1 / P1 — repeated signals interrupt cleanup.** `R3/supervisor_cli.py:63–67,150–163`; cleanup `confirmation-proof-binding-parent-repair-20261026-r4/execute_once.py:341–365`. After one signal enters exception cleanup, a second signal before forwarding TERM or during polling raises another `KeyboardInterrupt`. `except Exception` does not catch it. Cleanup/reap can end with a live worker; another signal during `finally` can suppress the receipt and handler restoration. No signal deferral protects cleanup/finalization.

2. **F2 / P1 — marker can be spent without a receipt.** `R3/supervisor_cli.py:8–10,70–71,156–162`. Signal or write/fsync failure after exclusive marker creation but before `claimed=True` leaves the marker present and the flag false. Finalization then skips the outer receipt. This trigger requires no worker launch.

3. **F3 / P2 — no cache postflight.** `R3/supervisor_cli.py:46–47,115–162`; `R3/worker_cli.py:54–55,90–100`. A file appearing in the registered cache, or removal of that cache after its initial check, is never checked again. Otherwise valid output can receive `accepted_pending_parent_postflight` with a violated empty-cache condition.

4. **F4 / P2 — exception exits skip integrity postflight.** `R3/supervisor_cli.py:87–88,115–162`. A signal or malformed/unreadable heartbeat jumps past input/source/interpreter/lease/marker postflight into cleanup and artifact inventory. A missing input during postflight also skips later checks. The partial failure receipt records no per-check unavailable results. Cleanup primitive bytes receive no final hash check on any exit.

5. **F5 / P2 — output consumer does not enforce all semantic bindings.** `R3/supervisor_cli.py:130–148`; producer `R3/probe.py:63–74`. A concurrent writer can replace output with a self-consistent bundle retaining checked vector/schema/digest fields but wrong parent/backend/torch values, recomputing the unpinned manifest hashes. The reader never compares those four fields, aggregate runtime/study/schema, or aggregate references against replica files. Such a bundle can receive outer pending acceptance. The pinned producer sets correct values; this finding concerns the independent consumer under output substitution, not observed wrong measurements.

## Verified source properties

- Concrete source, interpreter, checkpoint, integrity-receipt, acceptance, and vector hashes match registration. Author source manifest also matches. Accepted324 is `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`; acceptance is `3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd`.
- `execute()` actually invokes preflight before claim. It checks authority/schema, vectors, accepted parent, fixed 45/55/10/12-second limits, separate 6442450944-byte RSS/MPS caps, exact lease, conflicting leases, output/cache/cancel/marker state. Production registration excludes synthetic injection.
- Venv invocation remains `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python`; builder uses `.absolute()`, supervisor passes it unchanged, worker compares the un-resolved absolute path. Current stdlib inspection reports Python 3.12.15 and the project venv prefix. No dependency import/discovery was run by this review.
- Probe, fingerprint, and cleanup imports compile the same bytes whose hashes were checked. Probe flow seeds CPU then explicitly MPS, captures exactly three state-reference pairs, and binds all six seed fields. No model/environment construction, checkpoint deserialization, training, or evaluation appears in this flow. Checkpoint bytes are hashed only.
- Worker starts a new session. RSS sampling selects its process group; TERM/KILL cleanup uses bounded polling/wait. Worker stdout goes to a regular log, so no worker pipe `communicate()` drain exists. The `ps` helper uses `subprocess.run(..., timeout=0.2)`. Spawn-time signals are deferred until the child handle is assigned.
- Heartbeat checks bind run/registration/PID and enforce 2-second age, 0.2-second sampling, and separate resource caps. Worker heartbeat errors block normal publication. Manifest requires exactly three replica JSON files plus one aggregate receipt, and the reader checks their hashes and full vectors.

## Evidence limits

- No tests or reviewed code executed. Existing parent receipt/log report seven fake CPU tests under project Python 3.12.15. Those tests do not prove signal/cleanup/failure paths or actual MPS references. Author receipt mixes Apple Python 3.9.6 metadata with a project-venv command; parent replay is distinct evidence.
- Actual NumPy/Torch versions, MPS availability, resource behavior, cleanup timing, and generator-state digests remain unverified. First MPS heartbeat follows runtime imports; startup grace provides no MPS telemetry during those imports. There is no final forced memory sample after capture.
- The 55-second deadline bounds worker/cleanup decisions, not all blocking filesystem/hash/fsync work or receipt finalization. Strict total outer duration is not established by source inspection.
- `O_EXCL` prevents overwrite but writes final marker/receipt/commit paths directly. Interrupted writes can leave partial final JSON. The commit reader rejects malformed/incomplete bundles; publication is not atomic visibility or directory-fsync crash durability.
- `runtime_root` and `expected_venv_prefix` are present in registration but not consumed as assertions. Interpreter bytes and dependency version strings do not establish package-byte identity.
- At observation, all four active lease fields were null, marker/cancel/output absent, and both existing caches empty. The exact lease is not installed, so current supervisor preflight would reject before claim. No lease, marker, runtime, frozen input, or parent file was changed.
