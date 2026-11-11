r"""Record Python SpaceBot's overlay field (its room map) every 50 frames.

Run from dodge-native/learning:  ..\.venv\Scripts\python reports\timeline\web\tools\spaceview_ref.py 3
Writes web/parity/spaceview_s{seed}.bin: per sample, the frame (u32), the grid
side g (u32), then g*g float32 values, rows = y.
"""
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parents[2]))
from dodge.engine import Engine  # noqa: E402
from dodge.heuristics.space import SpaceBot  # noqa: E402

EVERY = 50
LIMIT = 3000

for seed in map(int, sys.argv[1:]):
    engine = Engine(seed=seed, difficulty=3, patterns=True, powerups=True)
    bot = SpaceBot()
    out = bytearray()
    for frame in range(LIMIT):
        state = engine.lane_state(0)
        bot.observe(state)
        a = bot.act(state)
        if frame % EVERY == 0:
            field = np.asarray(bot.overlay().field, dtype=np.float32)
            out += struct.pack("<II", frame, field.shape[0]) + field.tobytes()
        if engine.step(a):
            break
    (HERE / "parity" / f"spaceview_s{seed}.bin").write_bytes(bytes(out))
    print(f"seed {seed}: {len(out)} bytes", flush=True)
