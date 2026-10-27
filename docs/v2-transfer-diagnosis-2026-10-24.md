# Dodge v2 transfer diagnosis — parent reconciliation

The next supported step is a small, paired comparison of sampled and deterministic actions on frozen checkpoints. Longer D2 training is a plausible follow-up. The retained evidence does not yet establish that training time alone explains the remaining gap, or that action selection caused the initial transfer drop.

Taylor authorized this new Opus diagnosis after overnight closeout. No training, gameplay evaluation, benchmark, source repair, scheduler restart, or student work was launched. The original overnight report and failed-run receipts remain unchanged.

## What the evidence supports

- **D2 continued improving during its budget.** It completed 104 PPO updates. Fixed 64-seed evaluation survival rose from 295.25 to 1,148.78125 alive frames, and score from 1.4765625 to 8.9140625. The final complete evaluation improved again after the apparent middle-run plateau. Training episode summaries also improved. This supports further investigation of a longer learning curve; it does not forecast when a gate will pass.
- **D1 left pattern-specific inputs untrained.** Opus's CPU checkpoint inspection found zero change through D1 in type-embedding rows 7/8 and the global projection column for pattern visibility. D1 had no pattern rectangles. D2 adds these inputs alongside faster dynamics and a steeper score-driven difficulty ramp. Shared geometry and avoidance skills may still transfer; unchanged pattern-specific weights do not prove why transfer was weak.
- **The initial drop includes a pre-pattern problem.** The D2 entry argmax evaluation had 42/64 episodes ending within 200 alive frames. Those deaths precede pattern activation. Pattern novelty therefore cannot explain that entire initial drop. The first sampled training collection had only one such early death among 64 initial slots; 63 completed their initial episode during the collection and one remained alive beyond the collection window. The mean of 558.43 frames applies only to those 63 completers.
- **Patterns are common terminal context.** Of 7,915 completed D2 training episodes, 84.9% had admitted rectangles or visible warning lines in the terminal observation. This is a context measurement, not a killer attribution. The 430–639-frame bucket contains 3,567 deaths; it must not be called a verified first-pattern window.
- **No concrete source defect was identified.** Opus inspected the collector, GAE boundaries, deterministic evaluation, model, features, and episode bookkeeping. Its review does not prove those paths universally correct. KL/clipping increased and value fit weakened from its earlier peak; their causal role remains unresolved.

## Corrections to the Opus conclusions

1. **The action-mode gap is unpaired.** Training and development used different game seeds and different sampling/selection. Identical weights do not remove those confounders. The observed contrast motivates a matched test; it does not prove that argmax caused the entry collapse or that later checkpoints have the same problem.
2. **Terminal geometry cannot identify the killer reliably.** Native collision checks precede the player update, while returned features describe the post-step state. A lethal enemy can also be removed before that observation. Opus's proposed rule—terminal rectangle overlap means a pattern death, otherwise enemy/other—is rejected. Record terminal context as context. Reliable cause attribution requires separately reviewed collision-time instrumentation or an exact replay observer.
3. **Pattern timing includes startup.** Seven gameplay updates occur during the startup transition before the wrapper returns its initial observation. The native 420-tick delay gives an earliest wrapper gameplay activation at frame 413 when freeze does not delay it. A fixed 430–639 alive-frame bucket does not identify first activation across episodes; freeze and pattern selection also vary. The early deaths within 200 frames remain before pattern activation.
4. **Training totals use different units.** There are 104 completed optimizer updates but 105 accepted collections, including the last collection whose optimization was interrupted. Of 7,915 completed episode records, 7,863 belong to completed-update collections and 52 belong to the interrupted update's collection. All remain valid reward-audit inputs. Do not label all of them as belonging only to completed updates.
5. **The hours estimate is an extrapolation.** Opus projected roughly 4.9 hours from the eligible D1 checkpoint to the D2 progress gate by applying a stochastic-training score trend to the deterministic development target. Learning is nonstationary; descriptive survival slopes also differ across the run. Ordinary regression errors do not establish future learning uncertainty or statistically reliable deceleration. Treat this as a scenario suggesting another 30-minute run may be insufficient, not a validated budget or probability of success.
6. **Absence of a demonstrated gap is not equivalence.** A future paired comparison needs seed-level uncertainty and a practical effect criterion fixed in advance. Three stochastic repetitions on one game seed are not three independent game seeds. Failure to reject zero difference must remain inconclusive when the interval is wide.

## Recommended next diagnostic

Prepare and review a new diagnostic-only plan using three unique learner states: D2 entry, the last evaluated phase-96 candidate, and the complete phase-104 periodic checkpoint. D1 final and D2 entry have identical model weights, so a fifth redundant learner state is unnecessary. Exclude the interrupted checkpoint. Loading failed-run weights for diagnostic inference must not change their training/transition eligibility.

Use the same 64 development game seeds at D2, unchanged K=4, patterns/powerups enabled, and the 18,000-frame cap. Compare deterministic argmax with three fixed stochastic controller seeds. This gives 768 proposed episodes. Keep the original device and evaluation path for deterministic controls; CPU fallback would be a separately labeled experiment. Freeze inputs and check resource feasibility before execution, with a proposed 600-second wall limit and separate 6 GiB RSS/MPS guards.

The entry and phase-96 argmax controls must reproduce their saved per-seed rows before comparative interpretation. Phase 104 has no saved evaluation and is a new diagnostic baseline. Log action probabilities, chosen actions, margins, episode outcomes, and pattern-presence context. Retain unknown death causes. Aggregate stochastic replicates within each game seed and compare paired score/alive differences with uncertainty across game seeds.

If a meaningful late-checkpoint action-mode gap appears, investigate it before changing learner settings. If that gap is small with adequate precision and learning remains healthy, a new longer D2 experiment from the eligible D1 final is a supported option. Inconclusive results require an explicit next decision. Nothing automatically advances to training.

Any longer run needs its own reviewed budget and identity, new run seed, resource guards, and parent-owned terminal/budget anchor. The existing 1,800-second run must not be extended or relabeled successful. Same-phase resume remains disabled; all failed D2 artifacts remain ineligible. Rewards, architecture, qualification action mode, caps, and score/survival gates remain fixed. Further D1 or a bridging curriculum is not currently the first choice, but the evidence does not rule either out universally.

## Retained evidence

- [Original Opus diagnosis](../learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/diagnosis.md), SHA256 `05bea273ff427da852e6adf3fd2195740f3f2ee67136cab86c877a575f8392ab`.
- [Opus machine-readable result](../learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/result.json), SHA256 `15cf733c7754d236db8a7dd0c9c84b2e9e5b8f90b107016145cb383f6687159e`.
- [Parent audit evidence](../learning/runs/v2/postovernight-transfer-parent-audit-r1/).
- [Final D2 failure audit](../learning/runs/v2/milestone3-D2-parent-audit-r1/audit.json).
- [Overnight report](overnight-report-v2-2026-10-24.md).

Parent verified all 26 declared evidence hashes, seven reviewed source hashes, 11 output hashes, and all 75 current frozen source inputs. Hash verification establishes retained-byte identity; it is separate from checking the interpretation above.
