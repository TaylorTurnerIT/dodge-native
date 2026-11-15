# Dodge Danger Studio

Part II is isolated in `app.py`. It starts a capped native Rust run and embeds the trace viewer. The game scene comes from `NativeGame::render_into`, the shared CPU renderer used by the engine. The dashboard opts into compact hexadecimal pixel frames. Other trace, stream, and dataset runs omit pixels by default.

Build and run from the repository root:

```sh
cargo build -p dodge-danger
uvx --from marimo marimo run danger-studio/dashboard/app.py
```

Defaults are lookahead policy, seed 42, difficulty 3, patterns off, and 120 frames. The frame control has a 1,200-frame maximum to limit CPU cost. The danger overlay is off by default. Click the embedded canvas before pressing `O`, or select **Danger overlay**. HNN enemy paths show model predictions. The player path replays the policy-selected action from that frame, so it previews the planner's choice during manual review. It does not show a separate user-selected action. Observations are enabled only when the relevant environment setting enables them. The dashboard does not train models. In the native viewer, `--auto-dodge` cannot be combined with `--trace`.

Read-only Python and README references copied from the specified HNN source are in `danger-studio/hnn_reference_*.py` and `danger-studio/hnn_source_*README.md`. No data or checkpoints were copied. Noise and smoother outcome material is held for the study owner's release gate.
