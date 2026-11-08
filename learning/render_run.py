#!/usr/bin/env python3
"""Render a saved run (watch_heuristic.py --save-run) as an MP4.

The game is replayed from its seed and actions, so this runs far faster than
the bot played, and the same run can be rendered as often as needed:

    python render_run.py game.run.gz --out game.mp4                 # real time
    python render_run.py game.run.gz --out game.mp4 --speed 4       # 4x
    python render_run.py game.run.gz --out game.mp4 --max-mb 10     # as fast as fits
    python render_run.py game.run.gz --out game.mp4 --no-overlay

Speeding up keeps the frame rate and skips frames; a corner label shows the
speed. Each frame is checked against the checksum saved with the run, so a
replay that drifts from the game that was played stops instead of lying."""

import argparse
import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from dodge.display import GameWindow
from dodge.engine import Engine
from dodge.runfile import open_video, pixels_crc, read_run, unpack_overlay


MB_PER_SECOND = 0.12    # measured: 90 s of play with the overlay, CRF 32, 9.7 MB


def render(path, out, speed=1.0, overlay=True, scale=5, fps=60, crf=32):
    """Write `out`; return (source frames, video frames)."""
    settings, records = read_run(path)
    # Runs saved before the move to dodge_rl also name the old engine's options
    # (step_frames, pixels, execution); only the game's own settings carry over.
    engine_settings = {k: v for k, v in settings.items() if k in Engine.SETTINGS}
    window = GameWindow(scale=scale)
    font = pygame.font.Font(None, max(18, 6 * scale))
    label = None if speed == 1 else font.render(f"{speed:g}x", True, (255, 241, 232))
    writer = open_video(out, fps, crf)
    engine = None
    source = written = 0
    first = True
    for record in records:
        if record[0] == "game":
            seed = record[1]
            # the same calls the watcher made, so the same games come out
            if first:
                engine = Engine(seed=seed, **engine_settings)
                first = False
            else:
                engine.reset(seed)
            window.set_field(None)
            continue
        _, action, crc, packed = record
        pixels = engine.frame()
        if pixels_crc(pixels) != crc:
            raise SystemExit(f"replay drifted from the saved game at frame {source:,}")
        shown = unpack_overlay(packed) if overlay else None
        # every frame's field goes through, so its colour range moves as it did live
        window.set_field(None if shown is None else shown.field)
        # output frame j shows source frame floor(j * speed)
        while math.floor(written * speed) == source:
            window.show(pixels, shown)
            if label is not None:
                window.window.blit(label, (window.window.get_width() - label.get_width() - 6, 6))
            writer.append_data(pygame.surfarray.array3d(window.window).transpose(1, 0, 2))
            written += 1
        engine.step(action)
        source += 1
    writer.close()
    pygame.quit()
    return source, written


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--out", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-mb", type=float, default=None,
                        help="speed up until the file is at most this many MB")
    parser.add_argument("--overlay", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()

    speed = args.speed
    if args.max_mb is not None:
        # first guess from the game's length: a game with the overlay encodes to
        # about MB_PER_SECOND of video at real time
        frames = sum(1 for r in read_run(args.run)[1] if r[0] == "frame")
        speed = max(speed, math.ceil(frames / args.fps * MB_PER_SECOND / args.max_mb * 4) / 4)
    for attempt in range(6):
        source, written = render(args.run, args.out, speed, args.overlay, args.scale, args.fps)
        mb = os.path.getsize(args.out) / 1e6
        print(f"{speed:g}x: {source:,} game frames -> {written / args.fps:.0f} s, {mb:.1f} MB")
        if args.max_mb is None or mb <= args.max_mb:
            break
        # size is close to proportional to frames written; aim a little under
        speed = math.ceil(speed * mb / args.max_mb * 1.05 * 4) / 4
    else:
        raise SystemExit(f"still over {args.max_mb} MB at {speed:g}x")
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
