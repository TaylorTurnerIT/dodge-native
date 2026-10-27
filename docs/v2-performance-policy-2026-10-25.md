# Performance policy, 2026-10-25

Taylor removed score from future gates. [Version 3](teacher-qualification-v3.json) retains the survival thresholds: D2 progression requires mean alive frames ≥3,060; final qualification requires the existing survival ratios at both D2 and D3. Score remains a diagnostic and the training reward is unchanged. Native score comes from enemy deaths and pickups, not elapsed time.

Every user return includes survival Q1, Q4 and mean. Q1/Q4 mean the averages of the lowest/highest 16 of 64 episodes, ranked separately for each metric. Report checkpoint and cohort; use frames and 60 Hz seconds. Detailed performance reports also retain score quartiles and mean.

The retained best checkpoint has survival Q1 **648.25**, Q4 **4,508.8125**, mean **2,240.0** frames; score Q1 **3.5**, Q4 **46.59375**, mean **20.59375**. The final checkpoint has survival Q1 **556.125**, Q4 **3,507.6875**, mean **1,654.546875** frames; score Q1 **2.5**, Q4 **35.875**, mean **14.40625**. Both used 64 fixed development seeds and had 64 deaths, zero caps. Best is selected development evidence, not qualification.

Death attribution is unavailable for this run. Evaluation rows record termination and duration; native episode diagnostics record entity counts but no killer. Engine collision paths can kill through normal/kamikaze enemies, explosions, or lethal static/moving rectangles. Counts cannot identify which caused a particular death. Future telemetry should record the first alive-to-dead collision cause at the native collision site, preserve simultaneous contacts explicitly, and keep cause labels outside policy inputs.

Update: [native telemetry and a matched 64-game diagnostic](v2-death-telemetry-2026-10-25.md) now provide cause counts for checkpoint 000050 using an isolated new binary. Original records remain unchanged. Enemy bodies caused 32 deaths, pattern rectangles 31, and an explosion one; the representative episode hit a static rectangle.

Historical definitions, checkpoints and verdicts remain intact. The [v3 predicates](../python/dodge_rl/survival_gate.py) implement the survival-only progression and qualification thresholds. The v3 definition governs future registration; binding the training runner to the new policy and telemetry binary remains pending. The later user-authorized playback/telemetry work ran inference only; no new training was launched.
