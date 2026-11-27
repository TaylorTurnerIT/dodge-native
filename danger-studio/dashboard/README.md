# Dodge Danger Studio

Part II is isolated in `app.py`. Live and recorded modes display frames from `NativeGame::render_into`, the shared CPU renderer used by the engine. The dashboard opts into compact hexadecimal pixel frames. Other trace, stream, and dataset runs omit pixels by default.

Build and run from the repository root:

```sh
cargo build --release -p dodge-danger
uvx --from marimo marimo run danger-studio/dashboard/app.py
```

Live mode is the default. It uses one native process at a time, nice level 19, and at most two worker threads. New runs pause when the one-minute system load exceeds 8. The relay binds to an ephemeral localhost port and requires a random token. It validates run settings and stops idle runs after 45 seconds. The page retains at most 1,800 frames and 32 heat-map bitmaps.

Recorded mode preserves capped trace playback. It defaults to lookahead, seed 42, difficulty 3, and 120 frames. The frame control has a 1,200-frame maximum. The danger overlay is off by default in both modes. Click the embedded canvas before pressing `O`, or select **Danger overlay**. HNN enemy paths show model predictions. The player path replays the policy-selected action from that frame. It previews the planner's choice during manual review. The dashboard does not train models. In the native viewer, `--auto-dodge` cannot be combined with `--trace`.

Read-only references remain in `danger-studio/hnn_reference_*.py`. Training and analysis scripts copied from the specified HNN source are in `learning/hnn/`. No data or checkpoints were copied. Noise and smoother outcome material is held for the study owner's release gate.
