# Supervisor cleanup/deadline repair R3

Prepared for fresh parent independent review. No launch authority. R2, accepted worker/runtime and the indexed six final registrations are unchanged; 475 named immutable pins match. Parent state, lease and current launch paths were not inspected or changed.

`SUP-R2-01`: exceptional cleanup retains the direct child unreaped throughout TERM grace and KILL delivery, then waits/reaps within the remaining cleanup budget. No `waitid` assumption or new ownership handoff. Fresh post-reap identity guards remain unchanged. macOS `killpg(group, 0)` EPERM means present/unknown, never absent. Real regressions cover both launch-receipt failure and first-snapshot failure with empty anchors, a TERM-exiting leader and a TERM-ignoring descendant. Both require KILL, direct leader reap and absent owned group/process. Orphan descendant reap is established by OS process/group absence, not a claimed direct `wait` by the controller.

`SUP-R2-02`: total-deadline consumption stays sticky across caught read exceptions. Exhausted finalization skips worker-result/journal reads and removes large snapshots/accounting from partial receipts. The timer remains active through accounting/publication while budget remains. `observer-finalization.json` measures elapsed after the primary receipts; every elapsed field names its measurement boundary. Filesystem calls and fsync may overrun; no exact hard real-time I/O guarantee is claimed.

All original 21 controls remain: 11 fake and 10 real. One fake cleanup fixture and one real postflight control were adapted; two real regression tests were added. Final result: **11 fake + 12 real pass**. The combined cleanup test has receipt/snapshot subcases. Deadline controls use 3,400,000-byte valid synthetic journals and deliberately slow accounting; accounting is never called after deadline. Actual controller return times are 0.812 and 0.805 seconds for a 0.8-second total budget. See [suite receipts](real-test-receipt.json), [control reuse](control-reuse.json) and [first development failure](development-first-failure.json). The real suite uses a 55-second wall bound to accommodate retained TERM graces; the campaign's 1790/1800/10-second limits remain unchanged.

[Exact operational/control diff](exact-input-diff.patch), [source pins](source-pins.json), [reconstruction check](reproduction-check.json) and [provenance](provenance.json) accompany six inert R3 envelopes. `binding.py` (including atomic `save`), `terminal.py`, dependency binding, direct worker `Popen` and accepted runtime remain unchanged. Original exact source/lease/cache checks, raw exits, separate 6 GiB RSS/MPS limits, zero retries and parent terminal/checkpoint audit remain in force. Prelaunch scope digest and exact six indexed registrations are retained. No new restore probe, training, model/native/Torch/NumPy/MPS work, checkpoint deserialization, evaluation, promotion or delegation occurred.

Replay from project root into fresh owned report directories:

```sh
TASK_DIR="$PWD/learning/runs/v2/progressive1000-supervisor-cleanup-deadline-repair-sol-20261026-r3"
PYTHONPYCACHEPREFIX="$TASK_DIR/empty-cache" TMPDIR="$TASK_DIR/tmp" python/.venv/bin/python -I -B "$TASK_DIR/tests/run_controls.py" --output-dir "$TASK_DIR/replays/fake-01"
PYTHONPYCACHEPREFIX="$TASK_DIR/empty-cache" TMPDIR="$TASK_DIR/tmp" python/.venv/bin/python -I -B "$TASK_DIR/tests/run_real_controls.py" --output-dir "$TASK_DIR/replays/real-01"
```
