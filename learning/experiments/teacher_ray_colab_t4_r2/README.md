# DODGE-059 synthetic T4 compatibility

Successor to the failed DODGE-057 billing-admission attempt. Taylor authorized
cheaper GPUs for this non-training test. Original T4/A100 sources and failures
remain unchanged. DODGE-058 stays reserved for later native training work.

One T4 assignment, maximum 900 seconds and 8 existing compute units. Require a
positive live quote at most 3 CU/hour and exact owned assignment. An unchanged
balance is allowed: it proves neither zero cost nor financial freshness. The
parent conservatively adds elapsed time times the rate ceiling to observed
debit, stops work at 6 CU accounted cost, and reserves 120 seconds for teardown.
API errors, unknown/zero/over-ceiling prices, ownership loss and deadlines stop
work. Meter/network delays mean these controls are not a hard billing guarantee.

The source-only payload loads original420, checks named model/Adam migration,
float32 CPU/CUDA agreement at atol/rtol 2e-5, exact same-device zero-gate parity,
and one disposable optimizer step. No native environment, seed cohort, training
frames, held-out evaluation or trained weights. Watchdog limits are 300 seconds
and separate 6 GiB RSS/CUDA process memory. T4 success does not qualify A100
native training or establish learning performance.

Parent records our release request separately from assignment absence observed
before our request. Connection failure alone never proves Google removed a VM;
idle reclamation is not inferred. Receipt retrieval precedes release. Exact
assignment absence and accepted coordinator audit precede shared lease release.

Run CPU source fixtures from repository root:

    PYTHONDONTWRITEBYTECODE=1 python/.venv/bin/python -B learning/experiments/teacher_ray_colab_t4_r2/source_tests/run_ray_source_checks.py

No command in this README authorizes a cloud assignment. Frozen registration,
independent review, reviewed failed057 acknowledgment and exact non-null shared
lease handoff are required first. No allocation retry or GPU fallback.
