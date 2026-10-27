# Confirmation proof binding repair R3

Successor to `confirmation-proof-fixtures-luna-20261026-r2`. R2 and its review remain unchanged. This output repairs proof compatibility binding and pinned-byte execution.

`worker.py` now compares the replayed record evaluator SHA, canonical 13-member runtime-map digest, ranking manifest path and SHA to the confirmation registration, and rejects a ranking run ID equal to the confirmation run ID. Selection records and six ranking results are each read once, hashed, and parsed from those bytes. Both pinned module loaders hash one byte buffer, then compile and execute that same buffer.

Added negatives cover each compatibility field, same-run ID, validator tamper, preclaim rejection, and selection-record tamper during work followed by postflight rejection. Existing worker/launcher guards and contracts remain. No inference body or benchmark acceptance logic changed.

Run: `PYTHONDONTWRITEBYTECODE=1 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v test_selection test_runner test_heartbeat test_actual_lease_keys test_signal_assignment test_signal_windows test_supervisor_cleanup test_worker_lifecycle`

See `tests.log`, `source-hashes.json`, and `receipt.json`. Evidence is synthetic CPU/stdlib fixture coverage only. It does not read ranking quality or establish timing, runtime qualification, registration, launch authority, or paired-bootstrap acceptance. Future confirmation registration, timing, and paired-bootstrap gates remain parent-owned.
