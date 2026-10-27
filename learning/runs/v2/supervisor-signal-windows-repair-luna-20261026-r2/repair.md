# Supervisor signal-window repair

Copied integrated R5 sources and tests into this successor directory. Changed only `execute_once.py`, `test_runner.py`, and added `test_signal_windows.py`.

The runner installs TERM/HUP/INT handlers before marker claim, keeps them through postflight and receipt, ignores repeat signals during bounded cleanup, and masks those signals around `Popen` until the process handle is assigned. Exceptional post-claim paths write a truthful partial receipt once. Unknown PID and sampling failure cannot claim the process group is absent.

Fixed the copied test fixture's `GOLD`/`GOLD_SHA` restoration typo to `GOLDEN`/`GOLDEN_SHA`.

The full CLI CPU fake-process suite passed: 29 tests. The postflight signal case forks and reaps a same-group descendant before the worker exits; it verifies signal handling and an absent process group at receipt time. See [tests-final.log](tests-final.log) and [receipt.json](receipt.json) for command, hashes, and limits. No launch or runtime qualification evidence.
