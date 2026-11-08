# Learning

Python tools that play Dodge through the `dodge_rl` binding of the
`dodge-rl-env` crate. Everything here is run from this `learning/` directory.

## Setup

From the repository root, build and install the binding (needs Rust and a
Python 3.9+ virtualenv):

```sh
pip install ./crates/dodge-rl-env        # or: cd crates/dodge-rl-env && maturin develop --release
pip install -r learning/requirements.txt  # numpy, pygame, pytest
pip install -r learning/requirements-train.txt  # also torch, stable-baselines3 (training only)
pip install -r learning/requirements-dashboard.txt  # training + fastapi, uvicorn, altair, httpx (dashboard)
```

## SpaceBot

SpaceBot is a hand-written player: it simulates every enemy for 24 frames
under each of the nine actions, throws out the ones that collide, and picks
the one that leaves the most room to move.

```sh
cd learning
python watch_heuristic.py --headless --games 3 --seed 1 --next-seed increment   # prints frames lived
python watch_heuristic.py --seed 1 --overlay                                     # in a window
```

In the window, `O` shows or hides the bot's overlay (predicted enemy paths,
its plan, and its room map) and `Esc` quits. Useful options: `--difficulty
easy|normal|hard`, `--patterns`, `--no-powerups`, `--no-normal-enemies`,
`--no-kamikaze-enemies`, `--spawn-rate-percent`, `--max-frames`, `--games`.
`python watch_heuristic.py taylor-m0` runs the other registered bot.
A hard-difficulty game can last tens of thousands of frames.

## Training

`train_ppo.py` trains a PPO policy on the VelocityFlow observation, with
Stable-Baselines3 and the batched `dodge_rl` engine.

```sh
cd learning
python train_ppo.py --steps 250000 --envs 64 --difficulty hard --patterns --action-repeat 1     --name my-run --models-dir artifacts/models
python train_ppo.py --resume artifacts/models/my-run.zip --envs 64 --name my-run-2 ...
```

Each checkpoint `X.zip` gets `X.state.pt` and `X.manifest.json` beside it
(hyperparameters, env settings, reward weights, the `dodge_rl` binary's sha256
under the manifest key `dodge_rl`, the git commit and the parent checkpoint).
A resume restores the optimizer and the seed stream, and needs the same number
of envs. Reward weights come from `rewards.json` and the Training panel's
`training.json`, both local files that are not committed. `--help` lists the
rest: `--preset`, `--architecture`, `--retain-every`, `--budget-seconds`, ...

The engine ends a game at the `raw_frame_cap` and restarts it on a seed from
DodgeAI's own seed stream (`dodge/seeds.py`). Games follow this repository's
`dodge-core`, so survival numbers differ from the old `dodge_native` engine's;
the observation, critic features and counters are encoded identically, so old
checkpoints load and play.

## Tests

```sh
python -m pytest learning/tests -q
```

The engine tests skip if `dodge_rl` is not installed. The checkpoint tests
(`test_policy_parity.py`, `test_velocity_trunk.py` and `test_checkpoint_smoke.py`) read
local models from `learning/artifacts/models` and skip when they are absent;
set `DODGE_MODELS_DIR` to read them from another directory.

## Dashboard

A browser dashboard for training: live charts, the game, reward and training
panels, model save/load, a new-model dialog, evaluation and death-path jobs, and
a Heuristics dialog that opens a hand-written bot (SpaceBot, m0) in a window under
the current game settings, with its own overlay if you ask for it.

```sh
pip install -r learning/requirements-dashboard.txt
cd learning/web && pnpm install --frozen-lockfile && pnpm run build   # once
cd .. && python dashboard.py                         # http://127.0.0.1:8765
python dashboard.py --architecture velocity-flow-v2 --envs 32 --no-browser
```

`dashboard.py --help` lists the game-setting flags (they default to the last
saved `game-config.json`), `--host`, `--port` and `--models-dir`. The backend
serves the built page from `learning/web/dist`. For front-end work run
`pnpm run dev` in `learning/web` (Vite on port 5173, proxying `/api` and the
live socket to the dashboard on 8765); `pnpm run lint` checks the sources.

The death-path and pattern-replay jobs record a frozen policy on fixed seeds
with the engine trace (`slot_trace`) and replay any pattern appearance from its
seed and decisions, drawing it with `render`. A game that reaches the frame cap
ends as a truncation, and only an ended slot restarts, so a batch restarts its
ended slots on throwaway seeds.

Other tools: `watch_ppo.py MODEL.zip` watches a checkpoint play;
`play.py` is for playing yourself; `watch_heuristic.py BOT --record game.mp4`
or `--save-run game.run.gz` record a bot, and `render_run.py game.run.gz --out
game.mp4` turns a saved run into a video. Runs saved on the old `dodge_native`
engine cannot be rendered here: the new engine draws the player sprite larger,
so their pixel checksums fail at the first frame. Save them again.

## Not ported yet

The Colab setup (`colab/`, `colab_dashboard.py`) is still in DodgeAI.

## Credit

SpaceBot, its overlay and the other files under `dodge/` come from
LaunchSpark/DodgeAI by Lucas Starkey, which was MIT licensed and is contributed
here under this repository's CC BY-NC-SA 4.0 license. `dodge/heuristics/m0.py`
is a port of Taylor Turner's `m0_policy.rs`. `dodge/engine.py` is the adapter
to this repository's binding. `SOURCE-COMMIT-MAP.md` records the DodgeAI commit
each file was copied from.
