# Latest-versus-best paired D2 evaluation r3

R3 repairs native environment cleanup and persisted episode accounting after r2 failed on `VecDodgeEnv.close`. The native type has no `close`; evaluator cleanup drops references, matching frozen `dev_eval.evaluate`.

Preparation used only this directory. No source, runtime, checkpoint, orchestration state, lease, or prior candidate changed. R2 outputs remain preserved. No 512-episode campaign or training ran.

The campaign remains frozen at 512 episodes: 64 D seeds × two checkpoints × (one argmax control + three sampled replicates). Argmax controls run first. K=4, 18,000 raw-frame cap, MPS inference, per-environment common uniforms, CPU float64 inverse-CDF sampling, C4 primary contrast, 10,000 bootstrap draws with seed 764002, 590-second work limit, 600-second outer limit, and 6 GiB RSS/MPS caps remain unchanged.

R3 adds bounded native extension coverage: pinned `VecDodgeEnv` API inspection, one fixed-seed episode with cap 128 (32 K=4 decisions), startup/observation/step/cap terminal checks, and reference-drop failure cleanup. This fixture truncates at its cap. A separate pinned native terminal row from the existing development control file round-trips through the canonical row validator; it is historical harness evidence, not a new game episode or training evidence.

`supervisor.latest_resource_sample` ignores an incomplete trailing line, requires a complete sample no older than one second, and fails closed on malformed or stale complete samples. The run remains gated on fresh parent review, reconciliation, exact lease, and full preflight. Training preparation remains independent.

`freeze_artifacts.py` writes only protocol and input-manifest pins. Do not run `supervisor.py` until the parent installs the exact reviewed lease and clears the independent launch gates.
