DODGE-074 tests constant entropy pressure0.001 instead of0.01. It starts from original control12 with complete original Adam at LR3e-5. All other recipe, controller, memory and retention settings match accepted073.

This deliberately replays073's exposed training stream. Seeds stay unique within a trajectory. Different policy actions can change episode boundaries and the consumed ordinal prefixes. This is development optimization, not independent confirmation or identical action trajectories.

The first72 additional updates include512 consumed-development games every12 updates. Retain the highest observed mean if Q1 stays at least90% of control12 and early deaths stay within control12 plus ceil(2% of games). Beyond72, continue only under the existing guarded gain/stall rule. Preserve every learner+Adam checkpoint, original control12 and420. No elapsed-time cutoff applies.

073 completed successfully but all six play checks regressed. Its rising entropy motivates this existingDODGE-037 intervention. That diagnostic does not establish the cause of regression. Lower entropy may help or harm play.

Four CPU contract tests passed. Native, M1, controller, directory and lifecycle proofs are reused. Exact Luna and Haiku5.5 delta review, final source-commit binding, staging and live admission remain before invocation. No074 model load, native game, lease or optimizer step has occurred.
