# Current pair resource calibration R4 review (haiku-5.5, source only)

Frozen source: `learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/`.

**Verdict: BLOCK calibration probe.** No training impact. No finding reserves hardware or blocks independent training.

Constraints followed: source read and existing evidence only. Nothing was launched, reserved, leased, written to state, loaded from checkpoints, sent to MPS, run against the real env, probed, trained, or byte-compiled.

## Findings

1. **High, CONFIRMED. CPU preflight cannot produce the artifact the launcher reads.** `launch_once.py:162` runs `cpu_preflight.py`. That file has no `__main__` block and no argparse parser (`argparse` is imported at line 5 and never used). The subprocess exits 0 and writes nothing. `launch_once.py:168` then raises `FileNotFoundError`. Even with an entrypoint, `run()` writes `output_dir/cpu-preflight.json` (`cpu_preflight.py:61`), not `cpu-preflight-validation/cpu-preflight.json`. Every launch fails before `claim_once` (`launch_once.py:182`), so no marker is consumed. The README preflight command is a silent no-op. `cpu-preflight-run.log` came from an entrypoint not in the pinned source.

2. **High, PLAUSIBLE. Zero MPS samples fail a healthy run after the one-shot marker is claimed.** `probe.py:197` starts the sampler before the MPS model load. The R6 `_default_probe` reads `torch.mps.driver_allocated_memory()` every 0.25 s from sampler start. Pre-allocation samples can be 0. `probe.py:117` requires `all(value > 0)`, so the run fails after `claim_once`, and the single authorized probe is spent. Fix: require nonnegative finite samples everywhere, and positive high-water only after the MPS load. Confirm with a parent-owned measured run.

3. **Medium, PLAUSIBLE. 240-forward target may not fit the 45 s active bound.** Frozen evidence is 16 forwards and 272 guards over 2 passes, about 8 forwards and 136 guards per pass. Reaching 240 forwards needs about 30 passes, about 1920 rows with per-row fsync, and about 4080 guards, all inside 45 s. Slower passes fail closed at `probe.py:227`. Parent must measure.

4. **Low, CONFIRMED. MPS 6 GiB cap is post-hoc.** The launcher monitor sums current RSS only (`launch_once.py:221`). The MPS driver cap is checked only after the workload (`probe.py`). A runaway MPS allocation runs until the deadlines.

5. **Low, PLAUSIBLE. Unbounded communicate after SIGKILL.** `launch_once.py:274` has no timeout after SIGKILL. A hung child can exceed the 120 s outer bound and skip timeout evidence.

6. **Low, CONFIRMED. Stale status on post-check failure.** `launch_once.py:294` writes `child_reaped_postflight_pending` before post-child checks. A later failure cannot overwrite it, so failed runs look pending. Still fail-closed.

## Not verified

- 58 vs prior 60 pin member differences.
- R4 receipt mtime timezone correction.
- `authoritative_state_fields` contents.
- 136-guards-per-pass arithmetic against full `worker.evaluate` control flow. Consistent with the 272/2 evidence, not re-derived.
- CPU tests and preflight logs, not re-run.
- Ownership trace of R6 `__pycache__` files.
- Worker line numbers cited by function name only.

## Before any probe

- Fix finding 1: add a real entrypoint writing the path the launcher reads, or change the launcher to read what `run()` writes. Repin and re-review.
- Resolve finding 2 before spending a marker.
- Parent registers a new plan and reservation after fixes. This review does not authorize a probe.
