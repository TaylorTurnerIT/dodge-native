# Full-game seed-priority source review

**Result: blocking source findings.** Frozen package remains unchanged. Review scope was static source and reviewed registration r4; no launch, native constructor, accepted checkpoint load, model import, MPS probe, or game execution occurred.

## Findings

### P1 — Worker preflight receives source acceptance where launch approval is required

**Path:** `fullgame-seed-priority-experiment-luna-20261027-r1/binding.py:88-91`, `worker_cli.py:18`, `contracts.py:226-234`.

`binding.worker_command` passes `env["source_acceptance"]` to `--source-acceptance`. `worker_cli.main` passes that argument as `approval_path` to `contracts.preflight`. That function requires a `dodge_seed_priority_parent_launch_approval_v1` document with `approved_exactly_one_registered_run` status. The supplied document is instead checked by `binding.verify_bound` as `dodge_seed_priority_independent_source_acceptance_v1` at `binding.py:75-78`. Thus a correctly bound worker reaches preflight with the wrong document and fails the launch-approval equality check. The worker cannot pass its external gate.

The gate contract also conflicts: `binding.GATES` at `binding.py:11-13` has nine names; `contracts.GATES` at `contracts.py:28-31` has eleven different names. `binding.verify_bound` and `contracts.preflight` each require exact gate dictionaries. No approval object can satisfy both exact checks.

**Minimal reproduction:** inspect `binding.worker_command` argv, follow `worker_cli.py:18`, and compare the required `approval` dictionary at `contracts.py:231-234` with the source-acceptance schema at `binding.py:76-78`. Separately compare the two `GATES` tuples.

**Consequence:** all six registrations fail worker preflight, even after an outer parent envelope passes `binding.verify_bound`. The package cannot execute its reviewed worker call path.

### P2 — Package audit requires exit fields that observer never writes

**Path:** `fullgame-seed-priority-experiment-luna-20261027-r1/audit.py:20-24`, `observe.py:286-300, 324, 333, 363, 372`.

`audit.audit` requires `raw_worker_exit_code` and `raw_observer_exit_code` in both `observation.json` and `execution-result.json`. The observer records `observed_worker_raw_exit`, then writes its same record to both files. No package source writes either required `raw_*_exit_code` key.

**Minimal reproduction:** inspect a successful observer receipt from this writer or trace `observe.py`'s assignments and `b.save` calls. `audit.py` uses `.get` for absent fields, so its first raw-exit predicate is false and raises `raw worker/observer exit differs`.

**Consequence:** the package's own post-run audit rejects receipts produced by its observer. An external parent audit could replace it, but that does not make the frozen in-package audit pass.

## Checks that passed

- Source manifest SHA: `4c2432af888e56f1ffb4fa7a6bafb6a84f7897b34d63598fccea356fb6822cea`; all 48 member hashes match.
- Runtime manifest SHA: `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`; all 14 member hashes match.
- r4 draft index SHA: `b39d78f8ab1d470e5fdf2e6915c9842cf1da18a6c4062b73168715721de06ab3`; all six draft file hashes match. Drafts retain `launch_authority=false` and pending parent fields.
- Accepted pool file SHA and semantic canonical SHA are separately pinned and match: `5093727c2fdabd794267ccbc44a43b1fb29747b545cff645b66b0ad578180f04` and `5ed500167f97f17092fe8ca0fd581d3342366dde09f68f1fd8130db56e4f522f`.
- Independently recomputed 384 registered per-slot seed/component stream digests; zero mismatches. The design totals `64 × 256 × 60 = 983040` decisions. Each stream covers its absolute accepted parent offset plus 15,361 possible episode indices.
- Each draft preserves native `mode="evaluation"`/explicit-seed metadata, separately declares the pool training-only, binds the same pool and D4/D5 exclusions, and pins the replica's measured RNG reference. Treatment uses a 50% uniform floor and 50% hard component; priority is fixed and with replacement.
- PPO delta versus `progressive1000-opening-maintenance-runtime-parent-20261027-r1` changes explicit-pool seed validation and provenance metadata only. GAE remains bootstrap-on-truncation and stop-on-either-boundary. Step reward, objective, normal-start, raw-frame checks, and PPO math remain unchanged. Parent checkpoint/model and native bytes are pinned unchanged.
- Allowed Python `-B` TinyNet/fake-environment tests passed: `test_seed_priority.py` (4), `test_seeded_adapter_fake.py` (1), and `test_seeded_pipeline_cpu_fake.py` (2), using the registered Python 3.12.15 interpreter and package-local `PYTHONPATH`.

## Limits

CPU fake tests do not qualify MPS, native explicit-seed behavior, accepted checkpoint restoration, or game execution. No launch authority follows from this review. The legacy `tests/test_assembly.py` was not treated as production evidence: it exercises predecessor `CurriculumAdapter`/`preflight_reset` and deferred evaluator interfaces. The current runtime path uses `SeededTrainingAdapter` and fixed full-game rollouts; the two blocking findings above are on the reachable current worker/audit paths.

Source, runtime, and reviewed r4 index hashes matched again after review. No frozen inputs changed.
