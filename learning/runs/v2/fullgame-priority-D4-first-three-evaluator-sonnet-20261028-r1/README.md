# D4 terminal60 first-three concurrent evaluation (seed-priority study), revision r1

Isolated successor of the independently reviewed seven-policy evaluator `fullgame-priority-D4-evaluator-sonnet-20261028-r2` (source SHA `daaa54ba...`, source acceptance and review `fullgame-priority-D4-r2-review-haiku-20261028-r1`). That package, its r1 and every spent path are untouched and not reused. New eval run ID `fullgame-priority-D4-first-three-terminal60-evaluation-sonnet-20261028-r1`.

Preparation only. No launch, source or calibration approval is granted here. Nothing here loaded a model or checkpoint, constructed a native environment, ran torch/MPS, opened D4 outcomes or touched D5.

## Scope
Exactly three completed fixed terminal60 policies (checkpoint `worker-output/checkpoint-global-060-integrity.pt` + sidecar, full producer chain: registration, parent terminal audit, worker result, artifact manifest, lease release, parent execution, raw exit):

| id | home | parent terminal audit SHA |
|---|---|---|
| `replica-1-uniform` | `fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1/<run>` | `9d3902d8...` |
| `replica-1-opening_priority` | `fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/<run>` | `809b21f1...` |
| `replica-2-uniform` | same remaining-r3 parent | `2a9f1125...` |

No parent324. 3 x 1024 = 3072 episodes on D4 `0xD4000000..0xD40003FF`; D5 `0xD5000000..0xD50007FF` stays closed (B/E closed). Fixed contract is the reviewed evaluator's: normal starts, difficulty 2, patterns+powerups, cap 18000, action repeat 4, sampled categorical, no cutoff, RNG 2026102802 reseeded per policy, bootstrap seed 2026102801, 2000 draws, 95%. CPU/MPS semantics (MPS inference, CPU native simulation) unchanged.

Selection of these three is **completion availability authorized by the user, not performance**. Predeclared (policy-plan.json, registration `staging`, from `fullgame-priority-three-run-recovery-sonnet-20261028-r2/producer-home-remap.json`, hash pinned): later three `replica-2-opening_priority`, `replica-3-uniform`, `replica-3-opening_priority`. They are not required by this builder. All six training definitions and terminal60 endpoints are fixed before D4 opens; the later three are evaluated once, with identical D4 seeds/settings, in a separate reviewed run; these three are never re-evaluated; no partial result may change training, parent, seed vectors, checkpoints, stopping rule or selection.

## Report
Per policy: Worst=min, Q1=bottom-256 mean, Mean, Q4=top-256 mean, Best=max alive frames; milestones 1000/2000/4000/8000/12000/18000; death causes (and caps). Primary comparison: `replica-1-opening_priority` minus `replica-1-uniform`, paired over the same 1024 evaluation seeds, with conditional paired bootstrap intervals. `replica-2-uniform` is descriptive only (no priority partner): no pair-2, no three-replicate pool. Intervals are conditional on the fixed policies, not training-population evidence. D4 is development, not confirmation. No automatic retention or promotion.

Provenance limits unchanged: disjointness covers recorded accepted324 learner-family history; 122 historical file roles unresolved; no universal workspace nonuse claim; the live ledger is not pinned as history.

## Concurrency (user parallel exception)
User authorization `parallel-evaluation-authorization.json` (pinned, hash in registration `concurrency`) relaxes the one-global-active-campaign *thread guard* for this scope only. This package therefore:
- keeps its **own** ledger `evaluation-resource-ledger.json` (schema `..._resource_ledger_v1`) holding the exact evaluation lease (`kind fullgame_priority_d4_first3_terminal60_evaluation`, 32-hex owner token, RSS=MPS=6 GiB);
- **never writes, claims, clears or pins** the main `v2-orchestration/state.json`. It only reads it, and fails closed (`unregistered concurrent campaign`, watchdog latch `lease_changed`, TERM/KILL within the unchanged 10 s cleanup) unless `active_long_campaign` is null or a `fullgame_seed_priority_recovery_attempt` for study `fullgame-seed-priority-luna-20261027-r1` with `run_id` in the three runs of `registration-index.json` (pinned); `active_inference_*` must be null. Worker guard (0.2 s), observer watchdog and `verify_bound` each run this check; the terminal audit relaxes it to the own lease only and clears only the own ledger;
- keeps the 6 GiB RSS and 6 GiB MPS caps per campaign and the original worker/observer enforcement; nothing is raised. Shared GPU timing with training may vary; wall bounds are unchanged worst-case bounds;
- requires a scoped native-root caffeinate launch: `/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/empty-pycache <venv python> -B launch.py ...` (not the default 30-minute Claude Bash wrapper). `launch.py` runs the reviewed `power_guard.check()` (byte-identical to the recovery r2 copy) before spending anything.

## Limits (derived, not measured here)
- episodes 3072; constructors 3072; raw frames 3072 x (18000+13) = 55,335,936; native steps 3072 x 18000 = 55,296,000; resets 0; retries 0; guard, observer-journal and audit enforce independently. Per-episode cap 18000 gameplay frames.
- work = ceil(3 x 684.92 s / 15,487,746 frames x 55,335,936 + 10) = **7,352 s**; cleanup 10 s; postflight 120 s (kept from the reviewed r2; linear estimate of the prior 9.40 s overhead at this ceiling is 33.6 s); total = **7,482 s**. Worst-case bounds, not expected runtime: a comparable 3-policy evaluation is expected near 5 minutes (684.92 s for the prior full run at 15.5 M frames; shared GPU timing may vary).
- Host (read-only look at preparation): 48 GiB RAM, about 303 GiB free disk. No synthetic long throughput probe was run.

## Source reuse and build
Byte-identical to the reviewed r2: `observe.py` (watchdog, 120 s success-postflight inside `total`, 10 s cleanup), `execute_once.py`. Clean common evaluator/runtime (`progressive1000-opening-maintenance-runtime-parent-20261027-r1`, manifest `51aa867e...`, runtime `84e730ee...`) unchanged: same model/native/checkpoint/identity bytes. The earlier source review proved the inference members byte-identical to the r3 training runtime and the existing first producers; **first load of these checkpoints in the evaluator runtime is unproven here** (happens only inside the once-only run). Adapted: `binding.py` (policies, ledger, allowlist, staging), `comparison.py`, `paired_statistics.py`, `worker.py`, `terminal.py`, `audit.py`, `launch.py`, `monitor.py`, `build_registration.py`, `policy-plan.json`, `registration-schema.json`, tests. New: `power_guard.py` (copy). Interpreter: lexical `python/.venv/bin/python -B`, `PYTHONDONTWRITEBYTECODE=1`, owned empty cache prefix; module/source origins and PyO3 tuple boundaries are enforced by the reused `contracts`/`runtime_adapter` checks.

## Tests
`PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/tests-pycache python/.venv/bin/python -B tests.py`: 83 tests (stdlib fakes); 2 sealed-package tests skip until sealing, all 83 ran after sealing, 0 skipped. Includes real `worker.run` over fake evaluator/model/checkpoint/numpy/torch facades with real terminal validation, real `observe.main` driving a stub child with fake clock (success, over-headroom, work-deadline cleanup, registered training lease tolerated, unregistered concurrent campaign latched), real three-producer SHA/JSON chain checks, own-ledger lease install/clear with main state byte- and mtime-unchanged, and the real draft-build path with fake producers.
Honest limits (unchanged from the prior review): native `_production_rows`, real torch/MPS/numpy, checkpoint deserialization, `authenticate_runtime` and `binding.contracts()` over real model bytes are NOT exercised; the observer stub runs only on Darwin arm64. The statement that earlier source documents cited 48/53 tests is outdated: this package has 83 (the reviewed r2 had 68).

## Finalization (parent)
1. `python -B monitor.py readiness` or `build_registration.py --check`: three `ready`.
2. Inert draft `registration-draft.json` already built by `build_registration.py --output` (status `source_review_pending`, `parent_accepted false`, no authority). Rebuild only into a new package if inputs change.
3. Independent review of `source-manifest.json`; write source acceptance `{status: accepted_source_review_only, source_manifest_sha256}`.
4. Accept wall/resource calibration in a pinned record; `finalize_registration.py --draft ... --draft-sha256 ... --calibration-acceptance ... --calibration-acceptance-sha256 ...` → `registration-final.json`.
5. Gate acceptance (`fullgame_priority_d4_first3_evaluation_gate_acceptance_v1`, status `approved_exactly_once_fixed_terminal60_d4_evaluation`, every `binding.GATES` entry `passed`, exact `registration_sha256`, pinned review records).
6. Launch from the native root session under `caffeinate -ims` with `launch.py --registration ... --registration-sha256 ... --gate ... --gate-sha256 ... --source-acceptance ... --source-acceptance-sha256 ...`.
7. After terminal exit: `audit.py --envelope <pkg>/launch-envelope.json --envelope-sha256 <SHA>` (clears only the own lease). A failed run needs parent incident handling; never retry.
