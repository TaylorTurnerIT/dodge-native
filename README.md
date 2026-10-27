# Dodge Native

A standalone Rust/Macroquad build of the Dodge game.

This repository contains the playable native game, its deterministic core, and
the small command-line runner used to exercise it. The current learning work follows
the [privileged teacher and visual ViT specification](docs/SPEC_PRIVILEGED_VIT_RL.md)
and its [implementation plan](docs/implementation-plan-v2.md). Earlier experiments
in the separate [learning companion](learning/README.md) remain historical evidence.
The original reinforcement-learning project, Pemsa runtime, datasets, and trained
models are not included.

## Run the game

Install Rust from [rustup](https://rustup.rs/), then run on a system with
X11/OpenGL runtime libraries:

```sh
cargo run -p dodge-viewer
```

On NixOS, the checked-in `devenv` setup provides the Rust toolchain and native
libraries:

```sh
devenv shell -- cargo run -p dodge-viewer
```

Use the arrow keys to move. Press `R`, `X`, or `Space` to retry, `Z` to use
the alternate button, and `Escape` to quit.

The original cartridge is kept in `assets/dodge.p8` as the build-time source
for the native graphics data. No PICO-8 runtime is required.

## Attribution

Original game by [Artridge](https://artridge.itch.io/dodge).

## Training design notes

- [Current v2.0 specification](docs/SPEC_PRIVILEGED_VIT_RL.md): score-based PPO, non-clairvoyant typed entities, headless engine, and staged visual distillation.
- [Implementation plan and source corrections](docs/implementation-plan-v2.md): milestones, verification, and local Mac execution.
- [Complete supplied conversation](docs/Branch-DQN-vs-PPO-Explained-Google-Gemini.md): all six turns, including the source review and revised specification.
- [Original concept discussion](docs/Training-Vision-Models-Using-Privileged-Information.md): preserved verbatim as historical context.

## Check the build

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace
```
