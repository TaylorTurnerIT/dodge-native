# Learning

Python tools that play Dodge through the `dodge_rl` binding of the
`dodge-rl-env` crate. Everything here is run from this `learning/` directory.

## Setup

From the repository root, build and install the binding (needs Rust and a
Python 3.9+ virtualenv):

```sh
pip install ./crates/dodge-rl-env        # or: cd crates/dodge-rl-env && maturin develop --release
pip install -r learning/requirements.txt  # numpy, pygame, pytest
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

## Tests

```sh
python -m pytest learning/tests -q
```

The SpaceBot tests skip if `dodge_rl` is not installed.

## Not ported yet

Recording a window as video (`--record`) and saving a replayable run
(`--save-run`, `render_run.py`) are still in DodgeAI.

## Credit

SpaceBot, its overlay and the other files under `dodge/` come from
LaunchSpark/DodgeAI by Lucas Starkey, which was MIT licensed and is contributed
here under this repository's CC BY-NC-SA 4.0 license. `dodge/heuristics/m0.py`
is a port of Taylor Turner's `m0_policy.rs`. `dodge/engine.py` is the adapter
to this repository's binding. `SOURCE-COMMIT-MAP.md` records the DodgeAI commit
each file was copied from.
