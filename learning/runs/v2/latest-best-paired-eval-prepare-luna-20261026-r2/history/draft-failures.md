# Draft validation failures preserved

These messages are transcribed from the preparation terminal output. The early runs were not redirected to files.

## Evaluator fake observations draft

`TypeError: 'NoneType' object is not subscriptable`

The fake environment returned no next observation during its live-step path. The fake now supplies observations until the terminal truncation. This did not expose a harness defect.

## Lifecycle deadline test draft

`ValueError: Preflight exhausted registered work budget`

The fake clock advanced beyond the work deadline during preflight. The test now keeps preflight in budget and advances only at the worker monitor boundary.

## Publication assertion draft

The harness retained the failure in `publication_failure`; the test initially expected `postpublication_failure` for the pre-receipt publication guard. Assertion now checks the retained field actually written by the supervisor.

## Cancellation raw-exit assertion draft

`AssertionError: 0 != -15`

The injected child cleanup stub returned SIGTERM metadata but left its fake process result at the pre-cancel exit code. The stub now models the signaled process exit as `-15`, and the run_once receipt retains it.

## Cancellation exit-code draft

`AssertionError: 0 != -15`

The fake process initially reported its normal completion code after the cleanup stub ran. The fake now reports the signal exit (`-15`) so the receipt test checks raw cancellation retention.
