"""Record Python SpaceBot's action on every frame, to check the Rust port.

Run from dodge-native/learning:  ..\.venv\Scripts\python reports\timeline\web\tools\spacebot_ref.py 2 3
Writes web/parity/space_s{seed}.bin: one byte per gameplay frame (the action).
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parents[2]))
from dodge.engine import Engine  # noqa: E402
from dodge.heuristics.space import SpaceBot  # noqa: E402

for seed in map(int, sys.argv[1:]):
    t0 = time.time()
    engine = Engine(seed=seed, difficulty=3, patterns=True, powerups=True)
    bot = SpaceBot()
    actions = bytearray()
    while len(actions) < 18000:
        state = engine.lane_state(0)
        bot.observe(state)
        a = bot.act(state)
        actions.append(a)
        if engine.step(a):
            break
    (HERE / "parity" / f"space_s{seed}.bin").write_bytes(bytes(actions))
    print(json.dumps({"seed": seed, "frames": len(actions), "seconds": round(time.time() - t0)}), flush=True)
