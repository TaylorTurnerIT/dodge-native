# Full-game seed-priority r2 source review

**Source result: no blocking findings plus limits.** Final-registration review remains pending the parent-provided path and SHA. No r1 inputs changed.

## Gate and audit call paths

- `binding.worker_command` passes the launch-approval path and digest using matching `worker_cli` option names. `worker_cli` passes those values to `contracts.preflight`, which reads and validates the same document.
- `contracts.GATES` is the single canonical gate tuple. `binding` calls `contracts.validate_launch_approval`; it defines no competing tuple. Source acceptance remains a separate outer parent-binding check.
- Parent audit consumes `observed_worker_raw_exit` and separately supplied, directly reaped `raw_observer_exit_code`. It binds parent execution, envelope, and registration identities; verifies observer receipts and both process groups; checks cache and exact worker-output hashes; runs terminal accounting and postflight input checks; writes the durable audit before clearing the exact lease.
- Terminal global60 identity validation reads source/runtime pins from `identity.successor_runtime`, matching `successor_identity.learner_identity` output.
- Matched-pair validation allows the expected treatment/control seed and component stream hashes, plus run/arm-owned paths. Other differences fail closed.

## Observer receipt producer check

`observe.py` always enters its `finally` before successful return. It proves the worker group absent and writes both `owned_group_absent` and `worker_group_absent` from that proof into `execution-result.json` and `observation.json`. I passed the actual successful `parent-execution.json`, `execution-exit.json`, `observation.json`, and `execution-result.json` from `progressive1000-full-run-evaluator-parent-20261027-r2/dispatch/progressive1000-fixed-terminal-full-evaluation-20261027-r2/` into r2's `audit.validate_observer_receipts`; validation returned `True`. Its completed observation contains `worker_group_absent=true` and `owned_group_absent=true`.

## Frozen-input and scoped test checks

- Source manifest SHA `eba881154e3807c089eb0e3d2031ed6c8237dab1a57da3698d70ab6c6a91d1a4`; all 50 member hashes match.
- Runtime manifest SHA `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`; all 14 member hashes match and the manifest is byte-identical to r1.
- Draft index SHA `960a5789c41ab2f271028be666e54588e90a27bcf9c41e4b1440f1a0c5232144` matches.
- Eleven scoped CPU TinyNet/fake or stdlib tests passed: gate wiring (3), terminal checkpoint identity (1), pool schedule (4), seeded adapter (1), and seeded pipeline/accounting (2).

## Limits and remaining review

This clears only the frozen source gate. It does not authorize a launch or qualify MPS, native explicit-seed behavior, accepted-checkpoint restoration, or game execution. The actual final registration and its SHA still require review before any start.
