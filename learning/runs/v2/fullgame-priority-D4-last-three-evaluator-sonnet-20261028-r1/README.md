# D4 terminal60 last-three evaluation + offline six-model merge, revision r1

Second part of the predeclared six-model seed-priority study. Narrow isolated adaptation of the accepted first-part evaluator `fullgame-priority-D4-first-three-evaluator-sonnet-20261028-r1` (source SHA `489708da...`, registration-final `6912f25e...`, comparison `f08e8d7d...`, terminal audit `accepted_complete_fixed_terminal60_d4_evaluation`). The first part, its package and every spent path are untouched; its three models are never re-evaluated. New eval run ID `fullgame-priority-D4-last-three-terminal60-evaluation-sonnet-20261028-r1`.

Preparation only. No launch, source acceptance, gate approval or launch authority is minted here. Nothing here loaded a model or checkpoint, constructed a native environment, ran torch/MPS, opened any D4 outcome of the last three, or touched D5/B/E. The builder is inert: it refuses until all three producer audits and hash chains are accepted.

## Scope
Exactly three completed fixed terminal60 policies, all homes `fullgame-priority-three-run-recovery-sonnet-20261028-r2/<run_id>/`, checkpoint `worker-output/checkpoint-global-060-integrity.pt` (layout checked against the pinned `producer-home-remap.json`):

| id | status at preparation |
|---|---|
| `replica-2-opening_priority` | producer audit accepted |
| `replica-3-uniform` | producer audit accepted |
| `replica-3-opening_priority` | still training; builder refuses |

Selection is the predeclared remaining three of six, not performance and not checkpoint selection. All six training definitions were frozen before the first D4 open and are unchanged; D4 is open for the predetermined first three and now for exactly these remaining policy/cohort cells. D5/B/E stay closed. 3 x 1024 = 3072 episodes on D4 `0xD4000000..0xD40003FF`.

## Identical to the first part
Inference/source/runtime/model/checkpoint-loader/RNG/native semantics, D4 seed vector, evaluation RNG `2026102802` reseeded per policy, normal starts difficulty 2, patterns+powerups, cap 18000, action repeat 4, sampled categorical, bootstrap seed `2026102801`, 2000 draws, 95%, limits (work 7352 s, cleanup 10 s, postflight 120 s, total 7482 s; RSS=MPS=6 GiB; raw 55,335,936; steps 55,296,000; constructors 3072; resets 0; retries 0). `observe.py`, `execute_once.py`, `power_guard.py`, `dependency-binding.json` are byte-identical copies (tested). The first part actually ran 585 s (6.72 M raw frames) while training; recorded in the draft calibration as context only, not a projection input, no throughput probe.

## Minimal diff vs the first part
- `binding.py`: policies/pair/descriptive id, producer homes under recovery r2 plus a layout-vs-remap check, run/lease/ledger/schema names `last3`, `expected_staging()` now pins the accepted first part (hash only, no outcomes), main-state allowlist also checks the 6 GiB lease caps, authorization check names the first three (pinned document is unedited; no new authority).
- `comparison.py`, `paired_statistics.py`: primary pair replica-3 priority minus uniform; `replica-2-opening_priority` descriptive only here (its uniform partner is in the first part; no pair-2 or pooled replicate is fabricated in this standalone report).
- `build_registration.py`: first-part cost context; `policy-plan.json`, `registration-schema.json`, `tests.py` adapted. `worker.py`, `terminal.py`, `audit.py`, `launch.py`, `monitor.py`, `finalize_registration.py`, `seal.py`: schema names only.
- New: `merge.py`, `merge_tests.py`.

## Standalone report and concurrency
Pair: replica-3 priority minus normal (uniform), conditional paired-evaluation-seed bootstrap; replica-2 priority descriptive until merge. Own ledger only (`evaluation-resource-ledger.json`); main training state read-only, accepted only if null or one of the three registered recovery run IDs with kind/study/6 GiB caps; never written, cleared or pinned. The pinned user parallel exception is retained only if the run overlaps training or cleanup. Fail closed on any unregistered state; no retry protocol; own lease released only after the durable audit; never rerun after a fault. Launch from the native root under the exact owned `caffeinate -ims` helper (avoids the 30 min Bash wall kill).

## Offline six-model merge (`merge.py`)
`python -B merge.py --output six-model-merge.json` (new file in this package; refuses with exit 3 until both parts' audits are accepted). It verifies, before reading any row: both parts' audit/registration/source/artifact-manifest/lease/ledger/raw-exit/journal chains; the first-part pins; all six producers' terminal60 hash chains (checkpoint, sidecar, worker result, manifests, reproduced identity); identical fixed fields across parts (D4 seeds, settings, RNG, runtime, bootstrap, limits, provenance); six distinct model IDs, checkpoints, producer runs and identities; three replicas x two arms; same parent checkpoint; no overlap and no re-evaluation (the last part pins the first; the first predeclared exactly the last three). Then per model: 1024 exact seed rows, Worst, Q1 (bottom-256 mean), Mean, Q4 (top-256 mean), Best, milestones 1k/2k/4k/8k/12k/18k, death causes and caps; pairs 1/2/3 priority-minus-uniform; descriptive three-pair average; conditional paired-evaluation-seed bootstrap (shared indices across all six policies) whose pair-1 and pair-3 intervals must reproduce each part's own audited intervals. Labels: `training_population_inference: false`, `training_replicas: 3` (not 3072), intervals are conditional on the six fixed checkpoints, the average is descriptive. No selection, promotion or D5 claim.

## Tests
`PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/tests-pycache python/.venv/bin/python -B tests.py` and `... -B merge_tests.py`. CPU stdlib fakes only (same honest limits as the first part: native `_production_rows`, real torch/MPS, checkpoint deserialization, `authenticate_runtime` are not exercised). `merge_tests.py` builds fake audited parts and six fake producers and proves the exact six-policy identity/seed/settings merge, overlap/re-evaluation refusals, tampering, pinned first part, exact pair/average arithmetic and the conditional-versus-training uncertainty labels. Two sealed-package tests in `tests.py` skip until sealing.

## Activation steps (root)
1. When `replica-3-opening_priority` has its accepted audit: `python -B build_registration.py --check` (three `ready`), then `python -B build_registration.py --output registration-draft.json` (inert; status `source_review_pending`).
2. `python -B seal.py` if source changed; independent review of `source-manifest.json`; write source acceptance.
3. Parent calibration acceptance, `finalize_registration.py`, gate acceptance (`fullgame_priority_d4_last3_evaluation_gate_acceptance_v1`, every `binding.GATES` entry passed).
4. Launch from native root: `/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/empty-pycache <venv python> -B launch.py --registration ... --registration-sha256 ... --gate ... --gate-sha256 ... --source-acceptance ... --source-acceptance-sha256 ...`.
5. `audit.py --envelope <pkg>/launch-envelope.json --envelope-sha256 <SHA>` (clears only the own lease). A failed run needs parent incident handling; never retry.
6. `merge.py --output six-model-merge.json`.
