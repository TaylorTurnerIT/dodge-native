# Full-game seed-priority r2 lifecycle review

**No blocking findings in reviewed source lifecycle wiring or six final draft registrations.** R2 fixes the three r1 lifecycle blockers. All six registrations remain inert with `launch_authority: false`.

## Checks

- Source manifest SHA-256 is `eba881154e3807c089eb0e3d2031ed6c8237dab1a57da3698d70ab6c6a91d1a4`; all 50 listed source members match their pins. Runtime manifest SHA-256 is `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`; all 14 listed runtime members match, with no extra or missing members.
- `binding.py:82-85` passes parent launch approval and its digest. `worker_cli.py:13-18` sends those fields to `contracts.preflight`. `binding.py:67-72` separately checks the independent source acceptance. Both observer and worker use `contracts.validate_launch_approval` (`contracts.py:230-249`), so they share one exact gate schema.
- `audit.py:153-160` exposes `--envelope`, `--envelope-sha256`, `--parent-execution`, `--execution-exit`, `--output`, and optional `--lease-release`. `validate_observer_receipts` consumes the producer's `observed_worker_raw_exit` and parent wrapper's `raw_observer_exit_code` / `observer_directly_reaped`; it cross-checks execution and observation receipts (`audit.py:58-81`). No renamed or fabricated observer exit fields required.
- Checkpoint identity validation follows producer structure: `successor_identity.py:12-13` nests manifest hashes under `identity.successor_runtime`; `terminal.py:118-129` reads and validates that nested object.
- Normal preflight checks output and attempt-claim paths are unspent (`contracts.py:211-214`). Postflight and parent audit use `startup=False`; audit requires worker artifacts and exact process absence before writing durable audit and clearing the exact lease (`audit.py:104-149`).
- Both r2 draft indexes pin six registrations. Each replica's actual pair differences equal its declared fields: `arm`, `attempt_claim_path`, `launch_marker_path`, `output`, `run_id`, `slot_component_sha256`, and `slot_stream_sha256`.
- The `worker_group_absent` receipt requirement is satisfiable on success: `observe.py:325-333` is the enclosing `finally` block. It recomputes group absence and writes both group-absence fields before publishing execution and observation receipts. Success already requires group absence at `observe.py:300-303`.
- Confirmed against a real completed receipt from `progressive1000-full-run-evaluator-parent-20261027-r2`, whose `observe.py` SHA-256 matches r2 exactly (`95b8758eea4607f5f0812064f44ad5a26615a8a455ec0bf43d9c65bae991f81d`). Its observation and execution-result both report `status=completed_pending_parent_audit`, `observed_worker_raw_exit=0`, `directly_reaped=true`, `owned_group_absent=true`, `worker_group_absent=true`, and `postflight_inputs_unchanged=true`. Observation SHA-256: `263cb7611c6767e52e478b080cb4780a719935111ff567cef28e39543ec1c518`.

## Limits

The runtime manifest still identifies a copied release binary with modified Python runtime; release parity remains unqualified. `evaluation-contract.json` still records history `BLOCKED`, cohort `PENDING_NOT_RESERVED`, and launch authority false. The reviewed drafts are not final parent registrations. Current r2 review was source, pin, registration, and prior-receipt inspection only: no tests, preflight, launch, Torch/MPS/native imports, or model/checkpoint loads. Parent must still install and verify exact gates, lease, marker, registration, and authority before any one-shot launch.
