# Dodge Native

A standalone Rust/Macroquad build of the Dodge game.

This repository contains the playable native game, its deterministic core, and
the small command-line runner used to exercise it. It does not contain the
reinforcement-learning code, training adapters, Pemsa runtime, datasets, or
internal validation artifacts from the development project.

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

## Check the build

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace
```
