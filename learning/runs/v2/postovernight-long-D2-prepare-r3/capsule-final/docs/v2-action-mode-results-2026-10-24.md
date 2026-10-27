# Dodge v2 paired action-mode diagnostic — 2026-10-24

The diagnostic completed once: **768 episodes, 12 evaluations, exit 0, 48.044719833 seconds**. Both historical controls matched exactly. An independent retained-data audit passed with no findings, including a fresh numerical reconstruction of all paired bootstrap intervals.

Sampling improved the entry policy on the matched seeds. Later checkpoints showed no consistent sampled advantage. The latest complete checkpoint's deterministic policy averaged **1,341.578125 alive frames** and **10.515625 score**. These weights already existed; this diagnostic performed no training.

## Registered experiment

Taylor authorized the paired diagnostic after the overnight work had closed. The experiment used three frozen complete checkpoints: D2 entry, phase 96, and the phase-104 periodic checkpoint. The interrupted phase-104-plus-partial checkpoint was excluded. All failed-run weights retain their original training/transition ineligibility.

Each checkpoint ran deterministic argmax once and sampled actions with three fixed controller seeds, 64001/64002/64003. Every evaluation used the same 64 development game seeds, difficulty 2, patterns/powerups enabled, K=4, an 18,000-frame cap, and the original 64 independent B1 environments with batched policy inference over the sorted alive environments. Inference used the unchanged full teacher, float32 MPS and four Torch threads. There was no CPU fallback, episode retry, reset/filler, checkpoint selection, or qualification evaluation.

The registered wall limit was 600 seconds, with a separate 10-second owned-process cleanup reserve and separate 6 GiB observed RSS/MPS guards. Actual wall time includes supervisor startup through observed process exit. It is distinct from the internal terminal receipt's explicitly limited timing observation.

## Score and survival

Means below are rounded to three decimals. Each deterministic mean covers 64 episodes; each sampled mean covers 192 episodes, with three controller repetitions per game seed. Every episode ended in death; no episode reached its cap.

| Checkpoint | Role | Argmax score | Sampled score | Argmax alive frames | Sampled alive frames |
| --- | --- | ---: | ---: | ---: | ---: |
| D2 entry | Secondary | 1.477 | 3.117 | 295.250 | 602.594 |
| Phase 96 | Secondary | 8.914 | 9.393 | 1,148.781 | 1,222.599 |
| Phase 104, complete periodic | Primary | 10.516 | 7.828 | 1,341.578 | 1,075.161 |

The phase-104 deterministic survival mean is about 22.36 seconds at 60 Hz. It is a newly measured diagnostic result for the complete periodic checkpoint, not a result for the final interrupted weights and not a teacher qualification result.

## Paired uncertainty and interpretation

For each game seed, the analysis first averaged its three sampled repetitions, then subtracted its deterministic result. It resampled the **64 paired game-seed clusters**, using 10,000 shared-index bootstrap draws with fixed seed 764002. Intervals are exploratory 95% percentile intervals. Positive differences favor sampling.

| Checkpoint | Score difference | Score 95% CI | Alive-frame difference | Alive-frame 95% CI |
| --- | ---: | --- | ---: | --- |
| D2 entry | +1.641 | [0.945, 2.359] | +307.344 | [249.197, 367.778] |
| Phase 96 | +0.479 | [−2.055, 2.891] | +73.818 | [−164.445, 301.840] |
| Phase 104 | −2.688 | [−5.628, 0.039] | −266.417 | [−525.931, −19.698] |

All three predefined joint verdicts are **mixed/inconclusive**. The rule required both metrics' intervals to clear practical margins of one score point and 100 alive frames, or both to lie fully inside their equivalence margins.

- At entry, sampling improved both measured outcomes. The score interval's lower bound, 0.945, falls just below the one-point material margin, so the joint material-advantage rule does not pass.
- At phase 96, both intervals include zero. They do not establish equivalence or an advantage.
- At phase 104, sampled survival is lower, with its interval below zero. The score interval includes zero, and the full intervals do not meet the joint material-advantage rule for either mode.

This weakens the hypothesis that deterministic action extraction is the continuing bottleneck in the later policy. It does not prove the modes equivalent, rule out seed-specific behavior, or establish that longer training will pass the progress gate. No entropy, temperature, reward, architecture, curriculum or qualification change follows from this test.

The next candidate is a separately planned longer D2 learning-curve experiment with the current learner settings. Its budget and safe lineage still need a concrete plan. The present authorization covered this diagnostic only; no training has started. The original D2 run remains failed, same-phase resume remains disabled, and its diagnostic checkpoints cannot become eligible parents by virtue of this result.

## Runtime, controls and audit

The run covered **735,915 raw gameplay frames**, **184,280 decision traces/native step calls**, and **8,339 batched policy inference calls**. All 768 episodes ended in death, with zero caps. The trace records all nine action probabilities, chosen/argmax actions, entropy, margins and provenance. Pattern presence and first observed decision-boundary visibility are context only; death cause remains `UNKNOWN`.

The independent audit reconstructed all 768 rows and decision sequences, checked both historical controls field-for-field, and numerically reproduced all three paired bootstraps within `1e-10`. It verified 27 finalized outer artifact entries, nine campaign manifest entries, 422 input hashes, and absence of the recorded wrapper/supervisor/worker PIDs. Parent also verified the manifest/result bindings, inputs, observed exit/wall, and owned PID absence before clearing the completed lease.

Worker sampled/self-peak RSS was **630,472,704 bytes**. Maximum MPS driver allocation was **193,757,184 bytes**. The outer observer separately sampled a worker RSS maximum of **630,439,936 bytes** and did not independently measure MPS. These cooperative observations stayed below their separate limits; they are not an additive memory total or a hard OS allocation bound.

Before execution, 72 synthetic harness tests passed. Twelve discriminating regressions failed against frozen r1 and eight cancellation regressions failed against frozen r2. Frozen round-3 review found no remaining findings and retained 17 additional in-memory probes. Those preparation/review results are separate from the actual inference evidence above. The old 214-test result is not new v2 validation.

One additional file-only seal checker used unavailable `hashlib.file_digest` and failed after the campaign postflight checks. Its error is retained in `extra-verifier-failure.json`; a streaming SHA256 seal completed afterward. No model, environment, bootstrap, experiment setting or campaign was rerun to correct that checker. The earlier preparation inventory's active-stdout mismatch and corrected final inventory are likewise retained.

No gradients or optimizer updates, new learner checkpoints, eligibility changes, B/E qualification/replication, student work, scheduler restart, commit, PR, deployment or external message occurred. The no-training conclusion is supported by reviewed code, runtime receipts, raw traces and before/after identities; no independent OS syscall or optimizer-interception audit was performed.

## Exact evidence

- [Frozen protocol](../learning/runs/v2-orchestration/postovernight-action-mode-r3-protocol.json), SHA256 `90e3ae1cc8ba253e2e64a708f9b66ed59762e85668a15197d04d9265180ea741`.
- [Execution result](../learning/runs/v2/postovernight-action-mode-execution-r1/result.json), SHA256 `7fe12aa2716e6267d1f3626f1587694095ab5c48b21ebc39d07aca58cfda06c0`.
- [Authoritative campaign terminal receipt](../learning/runs/v2/postovernight-action-mode-campaign-r1/finalization-result.json), SHA256 `3deba5bb1ff2cc72217738de53478c4dd171ddb1cce5b1af0dac18579dccf920`.
- [Raw episode rows](../learning/runs/v2/postovernight-action-mode-campaign-r1/episodes.jsonl), SHA256 `e4a0cdbf36eedc451319ad1f9a828edff641295dcb1e1a5b50dee958761388cc`.
- [Raw decision traces](../learning/runs/v2/postovernight-action-mode-campaign-r1/decisions.jsonl), SHA256 `25b2900453c9f152f188e3ee3c2413c40fb1876cd373b37c569c31ed8e0208a3`.
- [Independent result audit](../learning/runs/v2/postovernight-action-mode-parent-audit-r1/audit.json), SHA256 `54d88390323a299b4b9489ec822056a0b4509306d31b404727e473e828141e96`.
- [Retained diagnosis and qualifications](v2-transfer-diagnosis-2026-10-24.md).
