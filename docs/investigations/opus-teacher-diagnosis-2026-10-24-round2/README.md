# Historical Opus teacher probes, round 2

These verbatim scripts and raw results preserve Opus 5.5's revised diagnosis after the four-arm representation comparison. The [methodology](../../investigation-methodology.md) and [current diagnosis](../../teacher-failure-diagnosis.md) explain how the findings affect subsequent experiments.

- [probe.py](probe.py) compares oracle-controlled and teacher-controlled trajectories on smoke seeds 2000–2002.
- [probe2.py](probe2.py) separates oracle action changes, continuation, and near-rest decisions on seeds 2000–2004.
- [opus-r2-closed-loop-probe.json](opus-r2-closed-loop-probe.json) and [opus-r2-onset-vs-continuation.json](opus-r2-onset-vs-continuation.json) retain raw measurements.
- [opus-r2-diagnosis.json](opus-r2-diagnosis.json) preserves the original interpretation, including claims qualified below.
- [manifest.json](manifest.json) records script/result hashes, checkpoint identities, and the original campaign's source manifest.

The scripts use fixed paths and output names, modify process-global thread settings, and lack production provenance checks. Preserve them as historical evidence; use a new output directory and compatible source for reproduction.

The independent parent audit identified these limits:

- The reported 0/48 recall uses both velocity magnitudes below `0.05`, not exact-zero velocity. Initial movement snapshots do have exact-zero velocity.
- The diagnosis treats the campaign's accumulated online `training_accuracy` as final training fit. That inference is unsupported; final-model training predictions were not measured by these scripts.
- All-neutral actions imply the neutral path under deterministic reset, but the JSON does not retain complete trajectory hashes.
- Rare training onsets were estimated from smoke trajectories, not counted on the actual training set.
- The first script retains only the final 20 frame records per teacher episode. Neither script proves a universal failure across all states or seeds.
- Raw elapsed fields total about 73.47 seconds, distinct from the agent's approximate CPU-time report. The aggregate exceeded the optional 60-second probe budget. No training or source edits were performed.

The observed failure to initiate avoidance is well supported on the tested trajectories. Rarity, distribution shift, velocity shortcuts, representation limits, and optimization remain explanations to distinguish experimentally.
