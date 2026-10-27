# D2 training v3 plan review (Haiku, readonly)

Scope: `learning/runs/v2/d2-training-v3-parent-prepare-20261025-r1/parent-plan.json`. Inputs hashed in `input-sha256.txt`. No runtime, tests, or adapter output inspected.

Current fresh D2 cohort (verified in `learning/runs/v2/critic-diagnostic-D2-20261025-r2/development-000048.json`): Q1=521.0625, Q4=2401.1875, mean=1101.9375 alive frames; 64 deaths, 0 caps.

## Findings

1. **high | parent-plan.json `budget_basis` | 80 updates: cumulative or new?**
   Trigger: parent checkpoint `checkpoint-000009-candidate.pt` already has `updates: 48` (run-result counters). Plan says `max_updates: 80` and eval at `[0..80]`, but never says whether 80 counts from the parent or from zero.
   Consequence: if new, 128 total updates against a 1600 s budget (~2.7× the measured budget). If cumulative, only 32 new updates run. Either way the budget math is wrong until fixed. Register one meaning and the eval index base.

2. **high | parent-plan.json `budget_basis` | Measured rate and sensitivity margin**
   Trigger: `796.987` s is observed inclusive process wall for 48 updates in `critic-diagnostic-parent-prepare-20261025-r3/parent-terminal-audit-r2.json` (worker 794.07 s). The accepted D1 run (`milestone3-D1-curriculum-r1/run-result.json`) gives 553.57 s for 32 phase updates (~17.3 s/update including its evals), not 16.6.
   Consequence: at the D1 rate, 80 updates ≈ 1384 s; +15% ≈ 1592 s before the 30 s eval allowance. Headroom to 1600 s is ~8 s. Any slowdown beyond ~15% makes the run incomplete, and incomplete weights are ineligible.

3. **high | parent-plan.json `budget_basis.extra_evaluation_budget_seconds: 30` | Eval cost is unbounded by the plan**
   Trigger: the 796.987 s measurement had evals at 0/24/48 (critic r2). The plan adds evals at 16/32/48/64/80 and uses D2 cap 18000. Measured eval throughput in the D1 accepted run is 122729 raw frames / 9.77 s ≈ 12.6k frames/s. At current mean ~1100 alive frames, one 64-episode eval is ~70k frames ≈ 5.6 s. At cap-hit survival (64×18000 ≈ 1.15M frames) one eval is ~92 s.
   Consequence: 30 s covers only ~10 s per extra eval. Any policy that survives longer, which is the goal, breaks the allowance and pushes past 1600 s.

4. **medium | parent-plan.json `budget_basis.finalization_reserve_seconds: 200` vs `docs/v2-m3-run-protocol.json` `receipt_reserve_seconds: 600` and `post_evaluation_reserve` formula**
   Trigger: plan reserve (200 s) differs from registered protocol reserves. If the adapter inherits the v1 rule "training_stop when remaining ≤ post_evaluation_reserve", the stop can fire before update 80.
   Consequence: early stop → incomplete → ineligible. The plan must state the reserve used and that reaching 80 is required, with no early stop from reserve logic.

5. **high | parent-plan.json `normal_checkpoint_contract` vs `docs/v2-m3-run-protocol.json` `stage_evaluation.end_immediately_on_progress_pass: true`**
   Trigger: v1 ends training as soon as a stage passes. The v3 plan requires completing 80 updates regardless of competence.
   Consequence: if the adapter reuses v1 end-on-pass, an early pass ends the run before 80 updates and the campaign is misclassified. The v3 adapter must explicitly disable it. The plan should say so.

6. **medium | parent-plan.json `fresh_u32_training_seed` vs protocol `transition_allowed_changes`**
   Trigger: the registered D2 `run_seed` is `5562881586070242562`. The plan replaces it with `810631976`. v1 forbids run_seed changes at transitions. The seed also appears in `learning/runs/v2-orchestration/state.json:1943`.
   Consequence: unless the v3 registration explicitly records this seed as a new registered run_seed and proves no episode-seed overlap with prior D2 runs, provenance is challenged. Confirm the orchestration entry is a reserved draw, not a used seed.

7. **medium | parent-plan.json `policy: "docs/teacher-qualification-v3.json"` | Provenance by path, not hash**
   Trigger: `docs/` and `python/` are untracked in git status. The plan names the policy by path only and does not hash `teacher-qualification-v3.json` or `survival_gate.py`.
   Consequence: the predicate or policy could change between review and launch without detection. Registration should bind these hashes: `bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae` and `11257111602f26e49fbc71afc6a51acb79434a3717bd8d6d36d1bbf87dfb8841`.

8. **medium | scientific scope | Competence reporting and selection**
   Trigger: evals at 16/32/48/64/80 on the 64-episode development cohort (seeds from 3489660928). Q1 and Q4 are 521 and 2401 on the current cohort, so the mean is noisy. The plan says "best development selection" must be distinguished, but it does not forbid choosing the best of the intermediate checkpoints.
   Consequence: picking a best-of-six checkpoint on the same cohort inflates the competence result. The provisional candidate should be the update-80 final checkpoint by default. Any other selection must be labeled as development-selected with no held-out claim.

9. **low | death/termination reporting**
   Trigger: current cohort is 64/64 deaths, 0 caps. Plan requires death causes per `teacher-qualification-v3.json` reporting, but the telemetry addition is only "phase_update on episode records".
   Consequence: death cause counts may be unavailable in the new adapter output. Confirm the schema carries cause counts including unknown and truncation separately.

## Verified, no finding

- `survival_gate.py`: D1 ≥1500, D2 ≥3060, D3 pair thresholds (6726.0523 / 4433.0418), and `qualification_passed` (point ≥1.1, lower >1.0) match `teacher-qualification-v3.json`. Score is not in the gate.
- Parent checkpoint `checkpoint-000009-candidate.pt` sha256 matches the plan (`ce9c03c8…0544f`).
- No historical checkpoint eligibility or validator is changed by the plan text. Old diagnostic/failed artifacts stay ineligible.
- No EV threshold was invented; no claim that this run must reach 3060.

## Verdict

Not ready to launch. Findings 1–3 are blockers for the budget and the 80-update meaning. Fix those, then review the adapter source separately.
