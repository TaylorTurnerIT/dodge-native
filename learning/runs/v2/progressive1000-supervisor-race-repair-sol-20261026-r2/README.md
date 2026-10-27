# Supervisor race repair R2

Preparation only; parent independent review and launch approval remain required. Writes are confined to this directory. Frozen R1, accepted worker/runtime, parent state and all six final registrations remain unchanged; see `preservation-after.json` and `source-pins.json`.

`SUP-R1-01`: `observe.py` directly owns the accepted worker's `Popen` from birth. `execute_once.py` now forwards to that same entry point; it creates no intermediate launcher. An unreaped direct child pins its kernel PID/group before any receipt or process-table snapshot. After reap, signaling requires fresh matching start/command/group anchors. Missing worker identity is `null` absence with `not_launched` ownership, never evidence of an absent worker. The independent observer monitors worker/descendant RSS and sampled MPS separately. Deadline alarms also interrupt stdlib preflight/finalization, preserving 1790 work / 1800 total / at most 10 cleanup seconds and the original five-second TERM/KILL policy within remaining time.

`SUP-R1-02`: `binding.save` fsyncs complete JSON in a same-directory staging inode, commits with an atomic non-overwriting hard link, then fsyncs the directory. Readers cannot see partial committed JSON. Existing or malformed committed receipts remain fail-closed. No worker retry was added.

Final controls: 11 fake controls pass, with seven unchanged and four adapted (`control-reuse.json`); 10 separate real stdlib controls pass (`real-test-receipt.json`). Real controls cover cancellation during direct ownership, failure before receipt/snapshot, TERM/KILL, descendant reap, work/finalization deadlines, partial/interrupted publication, conflicting malformed committed receipts, and source pins. Raw exits, exact owned groups and retained staging/failure artifacts accompany the receipts. Gates and control paths are synthetic; these controls do not qualify training, restore, native execution, MPS limits or campaign success. Development failures and superseded receipts remain under `development-*`.

`exact-input-diff.patch` reconstructs all changed/new executable and control files over R1; `reproduction-check.json` verifies all ten source-manifest members. `terminal.py` and `dependency-binding.json` are unchanged. No new restore probe, model/native/Torch/NumPy/MPS work, checkpoint deserialization, history search, evaluation, promotion or delegation occurred. Failed-run immutable/cache auditing remains a parent task, as in the frozen review.

Replay from the project root with fresh owned report directories:

```sh
TASK_DIR="$PWD/learning/runs/v2/progressive1000-supervisor-race-repair-sol-20261026-r2"
PYTHONPYCACHEPREFIX="$TASK_DIR/empty-cache" TMPDIR="$TASK_DIR/tmp" python/.venv/bin/python -I -B "$TASK_DIR/tests/run_controls.py" --output-dir "$TASK_DIR/replays/fake-01"
PYTHONPYCACHEPREFIX="$TASK_DIR/empty-cache" TMPDIR="$TASK_DIR/tmp" python/.venv/bin/python -I -B "$TASK_DIR/tests/run_real_controls.py" --output-dir "$TASK_DIR/replays/real-01"
```

Each suite enforces CPU/wall bounds and refuses to replace prior reports. The fake spawn guard remains intact. The real suite permits only owned stdlib helpers and read-only `ps`; it guards every signal target.

All six `templates/*.envelope.json` bind the indexed final registration bytes and R2 supervisor pins. They remain inert: null `started`, null launch-approval hash and `DRAFT_NO_LAUNCH`. Parent supplies the later exact per-run approval, separate shared-source acceptance, and identical finite monotonic `started` in envelope/worker CLI/exact four-field marker. Control paths remain outside worker output. Parent owns leases, markers, launch and terminal/checkpoint audit. Scope remains three matched pairs, accepted324, 60 updates at constant `3e-5`, fixed terminal60, zero automatic promotion; the supplied bounded historical evidence scope remains unchanged.
