# DODGE-012 fresh-seed control-frequency confirmation

This package prepares one bounded inference-only confirmation on checkpoint 420. It does not train, optimize, write checkpoints, select policies, or promote a candidate. The four arms differ only by registered selector and action repeat. Both repeat settings use the same parent-pinned successor runtime with raw-frame observation history preserved.

Parent protocol, authorization, D8 reservation, resource calibration, and runtime binding live in `learning/runs/v2/control-frequency-confirmation-parent-20261029-r1/`. They pin the sorted 256-seed cohort, controller seeds, eight-group order, per-condition and total budgets, checkpoint identity, exclusions, and the common runtime.

`screen.py` contains the parameterized complete-game collector, row validation, Q1 summaries, and seed-cluster bootstrap. Local `death_telemetry.py` preserves the accepted death-field function without importing the legacy evaluator dependency graph. `worker.py` owns checkpoint load, MPS inference, per-group categorical seed, memory counters, result publication, and RNG/weight checks. `observe.py` and `execute_once.py` are copied unchanged from the accepted fullgame D4 r2 supervision. `power_guard.py` is used in AC-only mode; launch refuses battery power and changes no macOS setting.

Build and review stay inert. Runtime import, checkpoint deserialization, native environment construction, MPS forward, and execution require parent source/runtime qualification and exact source, gate, lease, and one-shot gates. Parent terminal audit owns lease release. This package never clears the lease.

Q1 uses the bottom 192 of 768 sampled games or bottom 64 of 256 argmax games. Each sampled repetition also gets its own 256-game summary. Bootstrap draws resample the same 256 game-seed clusters across every condition and retain all three sampled controller repetitions in each selected cluster. These are controller repetitions, not training replicas.

Use `python3 run_tests.py` for synthetic-only analysis and worker-to-terminal checks. The fake worker runtime imports no Torch/native code and reads no checkpoint bytes.
