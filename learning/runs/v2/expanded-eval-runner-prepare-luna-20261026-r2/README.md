# Expanded evaluation runner r2

Preparation-only runner for the parent integration contract. `execute_once.py` performs registration, lease, source, candidate, cohort, review, cache, cancellation, and output preflight before an exclusive marker. It logs child output to an owned file, samples process-group RSS and worker MPS heartbeats, enforces a bounded stop/reap, and preserves outer receipts. `worker.py` forwards the external registration SHA and makes benchmark, ranking, or confirmation calls serially.

`build_registration.py` emits only a draft. It sets benchmark limits to 170 work seconds and 180 outer seconds without prior throughput. Ranking and confirmation require a byte-pinned successful two-repeat dev64 receipt; limits use twice measured elapsed/raw-frames scaled to each full raw-frame cap, plus 10 seconds cleanup. Final source review and parent lease remain pending.

Evaluator candidate path and SHA bind to the r4 publication repair. Its fresh source review is pending; this runner does not import it during preparation. No final registration, lease, marker, checkpoint load, native import, Torch/MPS, game environment, or campaign was used.

CPU-only fake-process suite: 16 tests pass. It covers benchmark, six-call ranking, two-call confirmation, preflight marker safety, golden mismatch, pin/lease changes, RSS/MPS stops, stale heartbeat, large logs, output collision, selection tamper, and child reaping. These tests are not qualification evidence.
