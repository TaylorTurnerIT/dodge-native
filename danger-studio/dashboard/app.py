"""Standalone Part II dashboard for the native Dodge danger demo."""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Dodge Danger Studio")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):

    mo.md("""
    # Dodge Danger Studio

    Part II runs the native Rust game and displays its shared CPU-renderer frames.
    Press **O** to show the arrival-time heat map, predicted enemy paths, and chosen-action path.
    """)
    return


@app.cell
def _(mo):
    policy = mo.ui.dropdown(
        options=["lookahead", "landscape", "hnn", "potential", "flee", "random", "neutral"],
        value="lookahead",
        label="Policy",
    )
    seed = mo.ui.number(start=0, stop=4_000_000_000, step=1, value=42, label="Seed")
    difficulty = mo.ui.dropdown(options={"1": 1, "2": 2, "3": 3}, value="3", label="Difficulty")
    frames = mo.ui.slider(start=120, stop=1200, step=120, value=120, show_value=True, label="Frames")
    mo.hstack([policy, seed, difficulty, frames], wrap=True)
    return difficulty, frames, policy, seed


@app.cell
def _(difficulty, frames, mo, policy, seed):
    import json
    import os
    from pathlib import Path
    import subprocess

    def render_panel():
        studio = Path(__file__).resolve().parent
        root = studio.parents[1]
        binary = root / "target" / "debug" / "dodge-danger"
        model = root / "models" / "physics.json"
        if not binary.is_file():
            return mo.callout(
                mo.md(f"Build the native demo first: `cargo build -p dodge-danger` (missing {binary})"),
                kind="warn",
            )

        args = [str(binary), "--policy", policy.value, "--seed", str(int(seed.value)),
                "--difficulty", str(difficulty.value), "--frames", str(int(frames.value)),
                "--horizon", "36", "--native-pixels"]
        if policy.value == "hnn":
            args += ["--physics-model", str(model), "--grid", "12", "--goal-every", "16", "--heat-every", "16"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=120,
                                    env={**os.environ, "DODGE_THREADS": "4"})
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "dodge-danger failed")
            payload = json.dumps(json.loads(result.stdout), separators=(",", ":")).replace("</", "<\\/")
            html = (studio / "dodge_visualizer.html").read_text(encoding="utf-8")
            html = html.replace("/*__TRACE__*/null", payload, 1)
            return mo.iframe(html, width="100%", height="900px")
        except Exception as error:
            return mo.callout(mo.md(f"**Could not run native Dodge.**\n\n```\n{error}\n```"), kind="danger")

    render_panel()
    return


if __name__ == "__main__":
    app.run()
