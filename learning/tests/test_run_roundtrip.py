"""A saved heuristic run replays frame for frame on dodge_rl."""

import os

import pytest

pytest.importorskip("pygame")
pytest.importorskip("imageio")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from dodge import engine  # noqa: E402
from dodge.runfile import pixels_crc, read_run  # noqa: E402
from render_run import render  # noqa: E402
from watch_heuristic import main as watch  # noqa: E402

pytestmark = pytest.mark.skipif(not engine.available(), reason="dodge_rl is not installed")


def test_saved_run_checksums_match_a_fresh_replay(tmp_path):
    path = tmp_path / "game.run.gz"
    assert watch(["space", "--seed", "7", "--headless", "--save-run", str(path),
                  "--max-frames", "240"]) == 0
    settings, records = read_run(path)
    records = list(records)
    assert settings["bot"] == "space" and records[0] == ("game", 7)
    frames = [r for r in records if r[0] == "frame"]
    assert len(frames) == 240
    # The first frame is the freshly started game, which a new engine reproduces.
    assert frames[0][2] == pixels_crc(engine.Engine(seed=7, **{
        k: settings[k] for k in engine.Engine.SETTINGS if k in settings}).frame())


def test_render_replays_a_saved_run_without_drift(tmp_path):
    path = tmp_path / "game.run.gz"
    watch(["space", "--seed", "11", "--headless", "--save-run", str(path),
           "--max-frames", "120"])
    source, written = render(str(path), str(tmp_path / "game.mp4"), speed=4, scale=1)
    assert source == 120 and written == 30
    assert (tmp_path / "game.mp4").stat().st_size > 0
