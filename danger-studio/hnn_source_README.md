<img src="assets/icon.svg" width="64" height="64" alt="">

# HNN-road-game

A marimo studio page for a game-theoretic Hamiltonian traffic visualizer. Four to eight
drivers cross an unmarked road, each with its own goal pit and its own view of the other
cars as velocity-aligned teardrop danger ridges. Goal points are draggable on the 2D map.

## Run

```console
uv sync
uv run marimo run studio/app.py
```

Open the URL that marimo prints. Use `marimo edit studio/app.py` to change the notebook.

## Layout

- `studio/app.py` — marimo notebook and page layout.
- `studio/visualizer.html` — self-contained 2D/3D simulation (Three.js, vendored).
- `studio/studio.css` — generated Stellar dark theme plus page styles.
- `studio/vendor/three.min.js` — Three.js r128, pinned for offline use.
- `studio/dodge_visualizer.html` — live and recorded playback page for the Dodge danger field.
- `studio/relay.py` — local relay that streams live frames from the Rust binary to the page.
- `dodge-native/crates/dodge-danger/` — Rust prototype: danger field, goal, and policies.

See `studio/README.md` for controls and the goal editor.

## Indexed pixel dataset

The `dodge-danger` example records indexed 128 × 128 framebuffers and engine labels. Build the nested repository, then run from this repository's root:

```sh
nice -n 19 env DODGE_THREADS=4 cargo build --release --manifest-path dodge-native/Cargo.toml -p dodge-danger --example pixel_dump
nice -n 19 env DODGE_THREADS=4 dodge-native/target/release/examples/pixel_dump hnn/physics_events.json hnn/data/pixels --frames 200000 --stride 1
```

The output directory must be empty. Each shard holds at most 20,000 frames as raw `uint8` bytes in `[N, 128, 128]` order, with one JSON label per frame. Open pixels with `numpy.memmap(path, dtype='uint8', shape=(N, 128, 128))`. Each label's `previous` list gives up to four prior saved global frame indices, newest first, from the same game. The default stride is four; use `--stride 1` for consecutive-frame stacks. Games cycle through difficulties 1–3, pattern settings, and HNN and exact lookahead policies. Pixel values use the standard 16-color PICO-8 palette. `hnn/pixels_peek.py` converts the first three frames of a shard to PNG.

`hnn.pixels_dataset.PixelDataset` requires NumPy and PyTorch. It returns consecutive indexed frames and per-channel center heatmaps, offsets, widths and heights, and effective velocities. Channel zero is the player; later channels follow `enemy_kinds`. The loader skips incomplete stacks and rejects unknown kinds. Centers outside the image have no dense target. Same-kind centers in one cell set `collision`, and only the first entity supplies regression targets. The original label is also returned. Target stride can be 1 or 2. No model training is included.
