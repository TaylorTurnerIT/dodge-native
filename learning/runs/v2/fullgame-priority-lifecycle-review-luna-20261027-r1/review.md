# Full-game seed-priority lifecycle review

**Three blocking source findings.** Frozen r1 cannot pass worker preflight or its terminal audit. The six r4 registrations remain inert drafts; none grants launch authority.

## Findings

### P1 — Worker receives source acceptance where preflight requires launch approval

- Evidence: `binding.py:88-91` passes only `--source-acceptance` and its digest. `worker_cli.py:13-18` forwards that file as `contracts.preflight`'s `approval_path`. `contracts.py:231-234` requires that file to have schema `dodge_seed_priority_parent_launch_approval_v1`.
- Trigger: Any observer dispatch that reaches the worker.
- Consequence: The worker reads the independent source-acceptance document as launch approval and fails before importing `worker` or constructing the runtime.

### P1 — Parent launch-approval gate schema conflicts across preflights

- Evidence: `binding.py:11-13,70-78` requires an exact approval object with nine gate names. `contracts.py:28-31,231-234` requires an exact object with eleven different gate names.
- Trigger: Supplying one launch-approval file to both observer and worker preflight, after fixing the argument wiring.
- Consequence: No single exact approval document can satisfy both checks; one of the two preflights rejects it.

### P1 — Terminal audit expects exit fields observer never writes

- Evidence: `audit.py:21-24` requires `raw_worker_exit_code` and `raw_observer_exit_code` in both receipts. `observe.py:286-288,313-318,372-379` records `observed_worker_raw_exit` and publishes observer status, but never writes either required field.
- Trigger: Parent runs `audit.py` after an otherwise successful observer run.
- Consequence: Audit raises `raw worker/observer exit differs` and cannot accept the completed run.

## Lifecycle state and limits

The r4 index is pinned at SHA-256 `b39d78f8ab1d470e5fdf2e6915c9842cf1da18a6c4062b73168715721de06ab3`. Source and runtime manifests match the reviewed task pins. The runtime manifest identifies a copied release binary with modified Python runtime and no release-parity qualification. `evaluation-contract.json` records history `BLOCKED`, new cohort `PENDING_NOT_RESERVED`, and `launch_authority: false`. These are outstanding qualification/authority gates, not evidence of launch readiness.

The copied `observe.py` bytes match `progressive1000-opening-maintenance-supervisor-parent-20261027-r1/observe.py` exactly (SHA-256 `95b8758eea4607f5f0812064f44ad5a26615a8a455ec0bf43d9c65bae991f81d`). This review did not run tests, preflight, or launch; did not import Torch/MPS/native code; and did not modify frozen inputs, registrations, checkpoints, leases, markers, or registry. Findings are static source review only.
