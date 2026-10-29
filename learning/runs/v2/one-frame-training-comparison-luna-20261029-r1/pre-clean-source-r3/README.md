# DODGE-013 inert capsule

This package prepares a parent-gated paired training comparison. It does not authorize launch, retry, checkpoint promotion, or automatic selection.

`build_registration.py` writes an inert registration after source and runtime manifests exist. `stream-audit.py` verifies only frozen seed inputs. `launch.py` requires independent source and parent gate acceptances, AC power, an empty bytecode cache, and the exact free lease. `observe.py` owns the single worker process; `audit.py` publishes a durable terminal audit before releasing the exact lease.

Formal arms restore checkpoint 420 and Adam independently, reset supported training RNGs to pair seed `202610290501`, and consume identical explicit uniform512 per-slot streams. Each stops after actual gameplay frames reach `11,796,480`, after optimizing the complete final vector call. Startup frames stay separate. Final checkpoints are fixed by target crossing. Evaluation covers three models, two repeats, and 1,024 reserved D9 seeds, with shared seed-cluster bootstrap.

Resource qualification is separate. It uses disposable learner state and cannot write checkpoints or feed weights into formal arms. No qualification or formal launch is performed during capsule preparation.
