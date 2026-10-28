# Three-run seed-priority recovery packet (prospective, no launch authority)

Study `fullgame-seed-priority-luna-20261027-r1`, six planned terminal60 endpoints. Retained, audited: replica-1 uniform, replica-1 opening_priority, replica-2 uniform. Replica-2 opening_priority was lost after 5 durable updates (Mac slept, tool wall timeout expired; audit `032e681c...`, lease release `14982746...`). The five-run sequence stopped per STOP-ON-FAULT; its Go is consumed. **No user approval exists for anything here.**

## Candidates (restart from the original accepted parent324 + Adam + same six-key RNG vector)
| run_id | registration candidate SHA-256 |
|---|---|
| `...-replica-2-opening_priority` | `5de0853263606f91b2706f545c98ff98a0ab32fc33b21589b650bf338776752b` |
| `...-replica-3-uniform` | `5ce87df408d1e86d834a77393475a41992684670646b237a5981f99d16f8072b` |
| `...-replica-3-opening_priority` | `95b1e065db9adad8f57df86a56f79b4c3c79c4fd23d11014698037fe43755600` |

Index proposal `5089e5c748ecfd243be482add3d41daf45fcd31baa77b566291ae1d47599ea16`; gates proposal `87633f8a2e8317c86fe0a85f025a9d6fbf6bc292509e8e63b0f215533bd880cc` (113 pins). Package manifest: `package-manifest.json` (file SHAs; its own SHA is what the review and gates bind).

Same run IDs and seed vectors/references/pool as the parent package's drafts; only private output/claim/marker/pycache paths and a fresh lease token (kind `fullgame_seed_priority_recovery_attempt`) differ (builder asserts exactly these five fields). The 5 discarded updates are extra infrastructure waste: not a continuation, not endpoint selection. Each registration is attempted exactly once, 0 retries.

## Pins unchanged
source `a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2`, runtime `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`, parent324 checkpoint `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`. Pool 512, LR 3e-5, 64x256x60 (983040 decisions), cap 18000, repeat 4, no cutoffs; work 3780 / total 3790 / cleanup 10; RSS = MPS = 6 GiB; raw/reset caps unchanged. D4/D5 unopened, parent324 unpromoted.

## Minimal diff vs proven parent (`diff-vs-parent.txt`)
- `watch_progress.py`: byte-identical.
- `remaining_plan.py`: run set (3), new lease kind/schemas, recovery constants (failure audit/release, checkpoint, receipt, stale-authority list, consumed user message).
- `start_remaining_one.py` (dispatcher, observer/wait logic untouched): binding module-origin assertion; spent-name list adds `progress-reports.jsonl`, `progress-alert.json`, `cancel`; shared pending-state path must be absent; gates must bind index proposal SHA + promoted index SHA, failure audit + release, exact checkpoint + receipt, an independent review pinned to the exact package manifest (and every manifest file still matches), no stale authority pins; authorization must be a different, later message and carry index-proposal and failure-audit SHAs; `power_guard.check()` before anything is spent.
- `power_guard.py` (new, read-only): on AC, dispatcher parent is exactly `/usr/bin/caffeinate -ims`, and it holds PreventUserIdleSystemSleep + PreventSystemSleep.
- `build_recovery_bindings.py`, `tests/test_recovery_bindings.py`: re-scoped.
- Excluded from gates: old five-run authorization, index, index proposal, gates, manifest, campaign proposal, activation record, first-run authority/launcher. Mutable ledger never pinned.

## Operational correction (not trainer code)
Launch each run from the ROOT native exec session as `/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<home>/empty-pycache <interpreter> -B start_remaining_one.py --run-id ... --index-sha256 ... --gates-sha256 ...` (exact lines in `activation-template.json`). The assertion lives for the whole dispatcher + observer wait on AC; no `-u`, display wake or `pmset` change. Not the default 30 min Claude Bash background wrapper; any tool timeout must exceed 3790 + cleanup + postflight (e.g. 4500 s, only if supported). Read-only monitor: `watch_progress.py`.

## D4
`producer-home-remap.json`: original D4 r2 paths and proposed recovery paths + candidate SHA for the three endpoints only. D4 r2 plan untouched (SHA pinned). Root later makes a reviewed successor/adaptation; all six endpoints stay fixed at 60 before D4 opens; no subset eval.

## Tests
`python -B run_tests.py`: 48 stdlib CPU/fake checks, all pass (`logs/test-summary.json`). No native/torch/MPS/checkpoint deserialization/reference rerun/training. Real caffeinate assertion could not be observed in the sandbox (see B4 in `launch-blockers.json`).

## Activation
See `activation-template.json` and `launch-blockers.json`. Final step after independent review: fresh explicit user approval of this concrete three-run plan; parent copies the verbatim text and the run/SHA pairs.
