# Three-run seed-priority recovery packet r2 (prospective, no launch authority)

Successor of the unlaunched r1 packet (kept untouched); only the read-only `power_guard.py`, its tests/docs and the rebuilt private candidate paths/tokens differ. Other r1 dispatcher/registration semantics are unchanged.

Study `fullgame-seed-priority-luna-20261027-r1`, six planned terminal60 endpoints. Retained, audited: replica-1 uniform, replica-1 opening_priority, replica-2 uniform. Replica-2 opening_priority was lost after 5 durable updates (Mac slept, tool wall timeout expired; audit `032e681c...`, lease release `14982746...`). The five-run sequence stopped per STOP-ON-FAULT; its Go is consumed. **No user approval exists for anything here.**

## Candidates (restart from the original accepted parent324 + Adam + same six-key RNG vector)
| run_id | registration candidate SHA-256 |
|---|---|
| `...-replica-2-opening_priority` | `651c22f671495a513a0256dea988da6dd0492a31b21cfb1a365a4c7ff88cd750` |
| `...-replica-3-uniform` | `743e81139d529ea4dc05544263ee0bd7f50123dca0ac04d825abb8d0e0cc4efa` |
| `...-replica-3-opening_priority` | `44c0bc4c6ffee5b17691c66991c33f3289a423f1e8f8fbfd93bf93ffeca9a086` |

Index proposal `4756aca3b2b0b4a0715ce483140e5c6cf8b7ef5e6a1613d96c68d8f5d5be38bd`; gates proposal `5d7855018c6966c429ce5854e6fbf210162eda249285e21e31736956606bfe3f` (114 pins). Package manifest: `package-manifest.json` (file SHAs; its own SHA is what the review and gates bind).

Same run IDs and seed vectors/references/pool as the parent package's drafts; only private output/claim/marker/pycache paths and a fresh lease token (kind `fullgame_seed_priority_recovery_attempt`) differ (builder asserts exactly these five fields). The 5 discarded updates are extra infrastructure waste: not a continuation, not endpoint selection. Each registration is attempted exactly once, 0 retries.

## Pins unchanged
source `a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2`, runtime `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`, parent324 checkpoint `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`. Pool 512, LR 3e-5, 64x256x60 (983040 decisions), cap 18000, repeat 4, no cutoffs; work 3780 / total 3790 / cleanup 10; RSS = MPS = 6 GiB; raw/reset caps unchanged. D4/D5 unopened, parent324 unpromoted.

## Minimal diff vs proven parent (`diff-vs-parent.txt`)
- `watch_progress.py`: byte-identical.
- `remaining_plan.py`: run set (3), new lease kind/schemas, recovery constants (failure audit/release, checkpoint, receipt, stale-authority list, consumed user message).
- `start_remaining_one.py` (dispatcher, observer/wait logic untouched): binding module-origin assertion; spent-name list adds `progress-reports.jsonl`, `progress-alert.json`, `cancel`; shared pending-state path must be absent; gates must bind index proposal SHA + promoted index SHA, failure audit + release, exact checkpoint + receipt, an independent review pinned to the exact package manifest (and every manifest file still matches), no stale authority pins; authorization must be a different, later message and carry index-proposal and failure-audit SHAs; `power_guard.check()` before anything is spent.
- `power_guard.py` + `probe_power_guard.py` (new, read-only; repaired in r2): on AC, a fresh `ps -axo pid=,ppid=,pgid=,command=` shows exactly one direct child of the dispatcher process, same process group, whose command starts `/usr/bin/caffeinate -ims <wrapped command>`; `pmset -g assertions` shows PreventUserIdleSystemSleep + PreventSystemSleep owned by that helper PID (name `caffeinate`). macOS caffeinate execs the utility and keeps a helper CHILD, so the dispatcher's parent (the app server) is normal and not inspected. Unrelated global caffeinates, wrong parentage/flags, battery and missing assertions are refused. r1 required the dispatcher PARENT to be caffeinate and failed the actual root probe (`parent-validation-20261028-r1/power-guard-*.json`); no trial was spent.
- `build_recovery_bindings.py`, `tests/test_recovery_bindings.py`: re-scoped.
- Excluded from gates: old five-run authorization, index, index proposal, gates, manifest, campaign proposal, activation record, first-run authority/launcher. Mutable ledger never pinned.

## Operational correction (not trainer code)
Launch each run from the ROOT native exec session as `/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<home>/empty-pycache <interpreter> -B start_remaining_one.py --run-id ... --index-sha256 ... --gates-sha256 ...` (exact lines in `activation-template.json`). The assertion lives for the whole dispatcher + observer wait on AC; no `-u`, display wake or `pmset` change. Not the default 30 min Claude Bash background wrapper; any tool timeout must exceed 3790 + cleanup + postflight (e.g. 4500 s, only if supported). Read-only monitor: `watch_progress.py`.

## D4
`producer-home-remap.json`: original D4 r2 paths and proposed recovery paths + candidate SHA for the three endpoints only. D4 r2 plan untouched (SHA pinned). Root later makes a reviewed successor/adaptation; all six endpoints stay fixed at 60 before D4 opens; no subset eval.

## Tests
`python -B run_tests.py`: 54 stdlib CPU/fake checks, all pass (`logs/test-summary.json`). No native/torch/MPS/checkpoint deserialization/reference rerun/training. Fake power-guard tests encode the actual observed helper-child topology plus negatives. The actual scoped probe is pending in the root native session (B4).

## Activation
See `activation-template.json` and `launch-blockers.json`. Final step after independent review: fresh explicit user approval of this concrete three-run plan; parent copies the verbatim text and the run/SHA pairs.
