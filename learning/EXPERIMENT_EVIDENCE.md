# Experiment source and evidence

`experiment-evidence-index.json` lists the archived source, configurations, tests, reviews, registrations, audit receipts, and compact logs under their original `learning/runs/` paths. Git tracks these selected files despite the run-directory ignore rule.

Checkpoints, native libraries, wheels, build trees, caches, large raw traces, and generated failure fixtures remain local. Source seals and checkpoint digests identify local inputs; this archive does not supply the model files or claim that every historical capsule can run on another machine. Preserve failed predecessors and their evidence.

Preparation, synthetic tests, measured runtime evidence, and parent acceptance remain distinct. Historical registrations and receipts do not authorize a new campaign. The accepted parent and current experiment state are recorded in `runs/v2-orchestration/state.json`; exact-once markers must never be reset or reused.
