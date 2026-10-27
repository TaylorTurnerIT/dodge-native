# D2 best180 all-candidate auditor r2

Read-only auditor for run `D2-best180-branch-luna-20261026-r1`. It binds the exact registered runner and launcher, checks each published checkpoint against its certificate and sidecar, and validates config, runtime, native, policy, parent, registration, metrics, progress, episode lineage, evaluation fields, and raw-frame accounting. Update 180's re-saved model, Adam state, and RNG must equal the accepted parent; the original parent remains authority.

## Provisional published-prefix audit

Run from workspace root with pinned Python 3.12 and `-B`:

```sh
PYTHONPYCACHEPREFIX=/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/empty-pycache-prefix python/.venv/bin/python -B learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/audit_candidates.py --provisional --output learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/provisional-result.json
```

This reads the consecutive stable published prefix from update 180. Missing or partial later certificates leave those updates pending; they do not indicate training failure. Provisional output has no terminal acceptance or best replacement authority.

## Full terminal audit

After normal training ends and all seven certificates are published, run:

```sh
PYTHONPYCACHEPREFIX=/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/empty-pycache-prefix python/.venv/bin/python -B learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/audit_candidates.py --output learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/audit-result.json
```

Full mode requires successful `execution-result.json` and `worker-result.json`, then calls frozen `execute_once.validate_outputs`. This supplies terminal checks only; parent review still owns acceptance and any replacement or continuation.

Focused controls:

```sh
python3 -m unittest -v learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2/test_audit_candidates.py
```

Five CPU-only negative controls use the actual checkpoint identity schema and reject corrupt mid-candidate bindings, counters, and resume lineage. Ranking control requires candidate 204 mean `1921.171875` to beat original 180 mean `1854.46875`; ties and lower scores retain original 180. Duplicate per-slot episode indices remain valid. The standalone import control checks that `execute_once.py` resolves `runner` to the pinned source. Another control verifies existing audit output cannot be overwritten.
