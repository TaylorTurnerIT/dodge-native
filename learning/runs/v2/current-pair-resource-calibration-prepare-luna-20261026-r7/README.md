# Current-pair resource calibration preparation R7

R7 is a CPU-only successor proposal for two defects observed in the single failed R6 actual probe. It does not authorize another hardware launch.

## Repairs

- `probe.py` consumes the exact `{sample, age_seconds, complete_records}` value returned by the frozen R6 `worker.read_latest_resource_sample`. The cap check keeps numeric, finite, nonnegative, inclusive 1-second freshness, startup zero, and separate 6 GiB checks.
- `launch_once.py` binds the validated pinset and publishes a terminal result after child reap and postflight. Result retains raw child status, process and resource evidence, pin counts, and truthful success/failure status.

`worker.py` and all earlier R6 source, receipts, markers, and result files remain untouched. R6 consumed marker and failed actual probe remain historical. No R6 retry occurs.

## CPU evidence

`test_calibration_cpu.py` exercises the real frozen resource reader with raw JSONL positive and negative controls. It calls the actual cap guard on the returned wrapper. Controls cover startup zero, 475136 bytes, over-cap, malformed, missing, nonfinite, and stale samples.

End-to-end launcher controls enter the real argument parser and `_main`, preflight subprocess, pre-spawn checks, `Popen`, wait, postflight, and terminal serialization. Only child executable and fixture-owned plan, pinset, reservation, authority, output, and marker are substituted. Success publishes raw exit 0; failure publishes raw exit 7. Existing CPU lifecycle negatives remain.

Run from this directory with:

```sh
D="$PWD"
mkdir -p "$D/owned-bytecode-cache"
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 NUMEXPR_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$D/owned-bytecode-cache" /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v test_calibration_cpu
```

The run uses the pinned project venv and owned cache prefix. It performs CPU-only evaluator fixtures and strict CPU checkpoint loads. It does not probe hardware, invoke MPS/game/env, train, write checkpoints, or mutate global state, leases, or reservations.

## Gate

Fresh independent review and parent registration are still required. The parent must create a distinct R7 reservation and verify the frozen plan, pins, review hashes, and current state before any marker or hardware probe. Existing 120-second outer, 90-second work, 10-second cleanup, separate 6 GiB RSS/MPS caps, 30–45-second active window, at least 240 forwards, 20 complete active samples, and 1-second freshness limits remain unchanged. No current 276 comparison or 512-episode campaign is claimed.
