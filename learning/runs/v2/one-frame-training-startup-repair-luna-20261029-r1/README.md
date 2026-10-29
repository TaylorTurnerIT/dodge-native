# DODGE-013 inert capsule

This is a source-only successor candidate after the R6 qualification observer failed before worker launch. It preserves the R6 runtime by reference and does not authorize another attempt.

`startup_regression.py` exercises the candidate observer against a temporary CPU-only child, then runs the frozen R6 observer against temporary fixtures to prove its two-argument helper call fails before launch. These fixture tests do not qualify resources or authorize a registration, lease, or marker change.

This package prepares a parent-gated paired training comparison. It does not authorize launch, retry, checkpoint promotion, or automatic selection.

`build_registration.py` writes an inert registration after source and runtime manifests exist. `stream-audit.py` verifies only frozen seed inputs. `launch.py` requires independent source and parent gate acceptances, AC power, an empty bytecode cache, and the exact free lease. `observe.py` owns the single worker process; `audit.py` publishes a durable terminal audit before releasing the exact lease.

Formal arms restore checkpoint 420 and Adam independently, reset supported training RNGs to pair seed `202610290501`, and consume identical explicit uniform512 per-slot streams. Each stops after actual gameplay frames reach `11,796,480`, after optimizing the complete final vector call. Startup frames stay separate. Final checkpoints are fixed by target crossing. Evaluation covers three models, two repeats, and 1,024 reserved D9 seeds, with shared seed-cluster bootstrap.

Formal arms also write recovery snapshots after completed PPO transactions cross each `3,932,160` gameplay-frame boundary. Snapshots preserve model, Adam, RNG, counters, native episode indices, and in-flight metadata; they do not capture full simulator state and do not authorize automatic resume. They remain ineligible and are never evaluated or selected. Qualification writes zero checkpoints.

Resource qualification is separate. It uses disposable learner state and cannot write checkpoints or feed weights into formal arms. No qualification or formal launch is performed during capsule preparation.
