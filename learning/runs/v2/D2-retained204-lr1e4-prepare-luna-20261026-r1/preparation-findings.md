# Retained BEST204 LR 1e-4 preparation

Prepared `D2-retained204-lr1e4-20261026-r1` from parent-authoritative BEST204. Candidate receipt schema stays `d2_retained_best_candidate_parent_receipt_v1`; whole-run receipt remains separate. Candidate is D2 phase 204, local 24, cumulative 252. Model, Adam, RNG, and resume state from later control updates are not ancestry.

Arm config changes only `ppo.learning_rate`: 0.0003 to 0.0001. The archived D2 config SHA remains `2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3`; the arm config SHA is registered separately. Runtime restores model, Adam, and full MPS RNG, proves equality, then changes only optimizer group LR. It asserts LR before and after each PPO update. Future actual worker must complete MPS RNG restoration before creating its environment.

Selected checkpoint trajectory baseline is 3352.0462366251204 seconds. Successful ancestor plus entire completed campaign cost is 4129.756859292152 seconds. The complete parent iteration observed outer time is 1177.4321468750002 seconds. New checkpoints preserve separate fields for trajectory and completed-campaign accounting.

Preregistered estimate is 1600 work seconds. It scales the control's 1177.4321468750002 seconds at 8224 optimizer steps to the arm's 9216-step maximum, then adds margin. Hard work/outer limits remain 1790/1800 seconds, with 10 seconds cleanup reserve and separate 6 GiB RSS/MPS caps. No relaxation or retry.

Preparation used CPU only. No environment or game-weight gradient/optimizer step ran. BEST204 model and Adam restored on CPU with exact fingerprints. Five counter, phase, frame, resume-index, and selection controls rejected mutations. Real dry preflight passed 13760 static pins; only the exact lease assertion was mocked. Current live state had no active lease when read. No lease was installed and no training launched.

This is an optimization trial, not a matched comparison with the old phase-180 control. Any result selection requires independent audit and strict improvement in same-64 deterministic-argmax mean alive raw frames. Score remains reward/reporting only. No qualification, D3, student, or visual authority.

Retained preflight failures: `attempts/preflight-attempt-01.log` through `preflight-attempt-03.log`; each defect was corrected before final passing preflight.
