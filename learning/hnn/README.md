# HNN training and analysis references

These project-authored scripts come from the `hnn/` directory of the HNN Road Game source tree at commit `65ba0dac4c4d96c64e203230022ef6c13e2952b1`. The source tree has no license file. This copy includes no third-party code, datasets, logs, checkpoints, or model weights.

## Script groups

- `physics.py` trains the enemy-motion model. `export_physics.py` converts its checkpoint to JSON, and `arrival_hnn.py` compares learned rollouts with supplied exact fields.
- `train.py` trains a learned-potential controller. `control_mlp.py` and `learn_observed.py` train controllers from observed examples. `noise_learn.py` studies controller robustness, and `noise-study/margin-off/action-hash.py` hashes actions for that noise study.
- `observed_dataset.py` and `pixels_dataset.py` prepare training data. `pixels_peek.py` inspects pixel samples.
- `fidelity.py`, `fidelity_accel.py`, `fidelity_births.py`, `fidelity_deaths.py`, `fidelity_hard.py`, `fidelity_kamikaze_rate.py`, `fidelity_pairs.py`, `fidelity_rect_lifetimes.py`, `fidelity_rect_oscillations.py`, `fidelity_rect_target.py`, and `fidelity_spawns.py` analyze supplied fidelity observations.
- `events.py`, `events_probe.py`, `events_probe2.py`, `bounce.py`, `bounce_curve.py`, `crush.py`, `fit_kamikaze_observed.py`, `spawns.py`, and `summarize_deaths.py` analyze observed events and enemy behavior.

## Dependencies and command syntax

The scripts use Python 3.10 or newer. Training and model inference scripts use NumPy and PyTorch. Most event and fidelity scripts use only the Python standard library; scripts that import NumPy need NumPy. Install required packages in your own environment. No data or model files are included.

Run commands from the repository root. Scripts that use argument parsers provide `--help`; other scripts document their inputs in the source. Examples:

```sh
python learning/hnn/physics.py --train /path/to/train.ndjson --val /path/to/val.ndjson --out /path/to/model.pt
python learning/hnn/train.py --train /path/to/train.ndjson --val /path/to/val.ndjson --out /path/to/potential.json
python learning/hnn/export_physics.py /path/to/model.pt /path/to/model.json
python learning/hnn/fidelity.py /path/to/fidelity.ndjson
python learning/hnn/arrival_hnn.py --val /path/to/physics_val.ndjson --model /path/to/model.pt
```

These are reference scripts. They do not run from the dashboard. No training or analysis was run during this migration.

## Excluded source

- `cluster/cluster.py` submits jobs through Taylor's configured HPC profile and includes cluster orchestration and account-related configuration access. It is excluded to avoid copying machine-specific submission logic and sensitive operational details.
