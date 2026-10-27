# D2 training v3 adapter preparation

Preparation only. No campaign, environment, evaluation, gradient, optimizer update, or training seed draw occurred.

`worker.py` consumes the distinct v3 registration, restores the accepted D1 model/Adam/RNG, runs up to 80 PPO updates, and evaluates at 0/16/32/48/64/80. It writes normal-schema provisional checkpoints and score-free v3 summaries. `adapter.py` validates registration pins, cache policy, parent transition evidence, complete update journals, and evaluation output. `launcher.py` owns one-use launch, cancellation, resource/deadline checks, process-group cleanup, and input/lease postflight. The startup rehearsal restores model, Adam, and RNG without creating an environment.

This preparation is **not ready for campaign execution**. Parent must freeze and hash the complete registration, then review outstanding launcher publication and test gaps. The launcher emits provisional worker evidence only; parent remains sole authority for terminal acceptance. The r3 rehearsal receipt was accidentally overwritten during this task and could not be byte-restored. The reconstructed old receipt has uncertain integrity. Do not rely on it.

Current named fresh development cohort: survival Q1=521.0625, Q4=2401.1875, mean=1101.9375 frames. Historical best development cohort: Q1=648.25, Q4=4508.8125, mean=2240 frames. Neither is v3 qualification evidence.
