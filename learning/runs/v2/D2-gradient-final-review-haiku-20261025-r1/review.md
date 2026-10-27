# D2 gradient final adapter and registration review (Haiku, read-only)

Scope: frozen adapter `learning/runs/v2/D2-gradient-runner-parent-repair-20261025-r3/` (`runner.py`, `execute_once.py`, four test files, `plan.json`, `README.md`) and registration `learning/runs/v2/D2-gradient-parent-prepare-20261025-r1/registration-r1.json` (sha256 `93d3dc7ac95b3670439d3989e82de563d6d2a856a68994b637670dbe4ff8bef1`). Read-only. No tests, training, rollouts, or edits were run.

Verified by read:
- Hashes of all eight adapter files match `preparation-receipt-r1.json` `source_hashes`. Registration sha matches the external pin.
- Registration validation checks parent sha, terminal receipt sha, native old/new pins, the PPO and gradient-alignment transition, the empty pycache prefix, and the exact lease.
- Worker, launcher, and `validate_outputs` checks cover entry restoration, update counters, the gradient-alignment identity, the clip identity, the 64-episode abandonment preservation, the entry-to-132 predecessor match, and the final cumulative counters.

## Blocking findings

No blocking findings.

## Non-blocking findings

1. **Low.** `execute_once.py:225`. The launch marker is written after a shape-only read of the registration (`execute_once.py:247` runs the sha-checked `load_registration` later). An unverified registration can create the output dir and `launch-marker.json`. Trigger: a wrong-sha registration passed to the launcher. Consequence: the single-use output dir is consumed before rejection. No success is latched. Fix: call `load_registration` before the marker write.

2. **Low.** `execute_once.py:325-326`. If `r.save(execution-result.json)` raises a non-`Cancelled` error, `return_code` is never assigned. Consequence: the exception propagates, the process exits nonzero, and no passed artifact is left. Acceptance is still rejected. No false pass.

3. **Low.** `execute_once.py:325` with the `except r.Cancelled` branch. A signal after `execution-result.json` is written with `status: passed` leaves that file saying passed, while `publication-failure.json` is written and the exit is nonzero. Consequence: contradictory artifacts. Nonzero exit plus publication-failure still rejects, which matches the stated policy.

4. **Low, labeling.** `runner.py:606` and `runner.py:669`. `current_iteration_wall_seconds` is worker-internal, measured from the inherited start. It excludes launcher preflight, process spawn, and finalization. The README says the cumulative wall adds the full outer iteration wall. Consequence: the worker's cumulative field understates the outer wall by seconds. The external observer's outer wall must stay the authority for the later attestation.

5. **Unverified, not a false pass.** `execute_once.py:204`. The frame conservation check `completed_frames + abandoned gameplay_frames == worker raw_frames` assumes `gameplay_frames` and `elapsed_raw_frames` use the same unit. Only synthetic fixtures test this. If the units differ, the run fails after the full work budget. This is a false rejection, not a false accept. The parent should confirm it against the actual runtime before the run.

## Scope limits

- I did not rehash the 13668 pins. The parent does that check.
- I did not verify the gradient-alignment numeric path or the MPS restoration path beyond reading the code. The parent's test logs and receipts cover them.
- I did not run the adapter tests.
- I did not check the runtime's `gameplay_frames` semantics (finding 5).
- Resource and budget enforcement is sampled at `Guard.check` points. An external RSS observer is required, as the registration states.
