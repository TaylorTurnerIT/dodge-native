# Danger Studio materials

`dashboard/app.py` is the standalone Part II dashboard. Build the native demo with `cargo build -p dodge-danger`, then run it with `uvx --from marimo marimo run danger-studio/dashboard/app.py`.

The dashboard defaults to lookahead, seed 42, difficulty 3, patterns off, and 120 frames. Its frame control caps runs at 1,200 frames to limit CPU cost. It opts into native renderer frames and compact hexadecimal pixel data. Default stream and dataset runs omit pixels. Click the embedded canvas before using `O` or playback keys. In the native viewer, `--auto-dodge` cannot be combined with `--trace`.

The dashboard and viewer use the tracked root model at `models/physics.json`.

For HNN, enemy paths show model predictions. The player path replays the policy-selected action from that frame, so it previews the planner's choice during manual review. It does not show a separate user-selected action. Noise and smoother study outcomes are withheld pending the study owner's release gate.
