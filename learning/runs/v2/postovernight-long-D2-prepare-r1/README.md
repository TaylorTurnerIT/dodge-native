# Standalone long-D2 preparation

This directory implements only the newly registered `v2-m3-long-D2-20261024-r1`
experiment. Preparation does not create a lease or launch a campaign. The parent
must reconcile the final synthetic evidence and independently review the sealed
capsule before creating the exact lease in `state.active_long_campaign`.

`long_d2.py` provides `preflight`, `run`, and an internal supervisor-owned `worker`.
There is no resume, alternate parent, device, seed, budget, or evaluation override.
Only the original successful D1 terminal candidate may initialize the learner.
The old failed D2 entry certificate is read as JSON control data only.

The unchanged historical `check_frozen` and `validate_transition` are called in
the worker with the old D2 config/identity and original project root. They prove
historical source/runtime/parent identity, not authorization for the new budget.
The new protocol, complete identity envelope and strict parent lease authorize
this experiment independently. No old validator or `Experiment` is bypassed.

The controller executes inside the read-only capsule and explicitly prepends
`ORIGINAL_ROOT/python`. Every loaded `dodge_rl` module must originate in the
original byte-pinned package and match its capsule mirror. Runtime receipts record
actual module origins. The original native extension absolute path is preserved.

`freeze.py` and the controller's `preflight` are stdlib-only. `freeze-receipt.json`
records the raw identity/config/protocol document hashes separately from the
canonical semantic identity hash embedded by unchanged `make_state`. The identity
contains all helper/test source hashes, complete long config, full historical
identity, exact D1 anchor and all original input pins. It excludes its own document
hash and the capsule manifest; the manifest includes the identity and excludes
itself. There is no circular hash dependency.

Use `invocation.json` for the exact argv and `required-lease.json` for the exact
15-field lease. Store task IDs/progress outside that lease. `preflight` may run
without a lease and creates no campaign output. `run` checks the lease before
creating its single-use registered output directory. The parent alone writes the
lease; preparation does not execute the run command.

The supervisor starts T0 before normal imports. Worker deadline is T0+7140,
absolute normal-publication deadline T0+7200. Failure-only owned cleanup is at
most 10 seconds. An independent alarm and supervisor bound blocked worker calls.
Resource and lease failures latch; RSS and MPS remain separate 6 GiB observations.
Signals remain blocked through creation/assignment of the owned PID. Publication
requires a reaped leader and positively empty group; every normal publication/hash
checks the absolute deadline. Cancellation latches survive cleanup and stream close.

Entry evaluation is phase update 0; further evaluations occur only at multiples
of 16, always after a checkpoint. Periodic checkpoints occur at update 8 within
each block. U/E reserve estimates only grow. If a full block no longer fits,
closure preserves the last complete state without an off-cadence evaluation.
Checkpoints preserve live training environments/observations and training RNG.
All artifacts remain training-parent ineligible and teacher-unqualified.

Exit 0 means complete with D2 progress gate passed. Exit 2 means complete with
budget closed below gate. Exit 1 means failed. A gate pass only identifies a
candidate for a separate future parent audit; it opens no D3/B/E/student work.
The terminal receipt is authoritative and binds the stable manifest/run result.
Its wall observation excludes its own write and process exit; the parent must
observe actual exit/wall. Unproven writer absence or late publication revokes the
manifest and writes an explicit failure receipt.

Tests are synthetic: fake clocks, fake learner/state objects, AST-loaded unchanged
legacy rejection paths, real OS-owned stdlib fake workers, and deliberate retained
broken helper copies. No actual teacher, native environment, MPS, gameplay, model
inference, checkpoint deserialization, or gradient updates occur in preparation.
Counts and scope belong to `test-receipt.json`; historical test totals are not reused.
Development failures and negative-control attempts remain retained. Early source
reconstructions are labeled separately from contemporaneous snapshots.
