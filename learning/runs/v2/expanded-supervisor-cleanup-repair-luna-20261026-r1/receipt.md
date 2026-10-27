# Supervisor cleanup repair receipt

Base: `expanded-eval-runner-pipeline-repair-luna-20261026-r3/execute_once.py`; preserves R3 `active_long_campaign` guard. Scope: supervisor source plus fake-process tests only.

Changes: bounded SIGTERM/SIGHUP handlers route through termination, reaping, partial receipt, then restore prior handlers. Repeated signals during cleanup are ignored. `ps` sampling errors preserve their failure reason; process-group absence remains unknown when sampling fails. Cleanup sends process-group SIGTERM then SIGKILL within one 10-second bound and reaps the direct child independently of `ps`. Outer receipt path is checked before marker claim.

Verification: `python3 learning/runs/v2/expanded-supervisor-cleanup-repair-luna-20261026-r1/test_supervisor_cleanup.py` — 20 passed. Full output: [tests.log](tests.log). Fake subprocesses only.

Source SHA-256:

- R3 base `execute_once.py`: `ac33b251bde6628b557bf92b3c72d16445467c92f25dc3163b0b87dc6e2fe787`
- repaired `execute_once.py`: `d9d8b2fe6788264365fc7891db59684c4625dfea78de0e424834ab7f69704393`
- `test_supervisor_cleanup.py`: `3c2603197c5547fd7716aee94adbc073ce329ed0d300b616eea6a8882b856b26`
- `execute_once.diff`: `4f242ae5b971305036238d7919e158a28ee7a9e71e739d6fe560a89b45f1f9e5`

Limits: SIGKILL cannot be handled. Process-group absence is not asserted when `ps` fails. Tests prove fake subprocess behavior only; no native, Torch, MPS, game, training, real lease/marker, final registration, or launch was run. Builder, worker, and benchmark receipt schema were not changed.
