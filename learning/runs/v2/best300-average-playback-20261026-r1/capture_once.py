"""One inference-only representative replay against a copied frozen runtime."""
from pathlib import Path
import hashlib
import json
import os
import resource
import sys
import time
import traceback
import zlib

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT / "plan.json").read_text())
START = time.monotonic()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def guard():
    authority = json.loads(Path(PLAN['state_path']).read_text())
    if authority.get('active_inference_diagnostic') != PLAN['expected_lease'] or authority.get('active_long_campaign') is not None:
        raise RuntimeError('Playback lease changed or concurrent training')
    if time.monotonic() - START > PLAN["limits"]["wall_seconds"]:
        raise RuntimeError("Playback wall budget exceeded")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > PLAN["limits"]["RSS_bytes"]:
        raise RuntimeError("Playback RSS budget exceeded")


def main():
    for name, expected in PLAN["runtime"].items():
        assert digest(OUT / name) == expected, name
    assert digest(PLAN["checkpoint"]) == PLAN["checkpoint_sha256"]
    assert digest(PLAN["certificate"]) == PLAN["certificate_sha256"]
    sys.path.insert(0, str(OUT / "runtime"))
    import numpy as np
    import torch
    from dodge_rl import VecDodgeEnv
    from dodge_rl.checkpoints import load_checkpoint
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    torch.set_num_threads(4)
    assert torch.backends.mps.is_available()
    state = load_checkpoint(Path(PLAN["checkpoint"]), expected_sha256=PLAN["checkpoint_sha256"])
    model = OmniscientEntityTeacher().to("mps")
    model.load_state_dict(state["model"], strict=True)
    model.eval()
    model.requires_grad_(False)
    expected = PLAN["expected_episode"]
    env = VecDodgeEnv(batch_size=1, action_repeat=2, difficulty=2,
                      patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000,
                      num_threads=1, chunk_size=1, render_pixels=True,
                      auxiliary_targets=False, seeds_by_slot=[[expected["seed"]]],
                      excluded_seed_ranges=[(0xB0000000, 0xB00003E7),
                                            (0xD0000000, 0xD000007F),
                                            (0xE0000000, 0xE00003E7)])
    observation = env.observations()
    frames = bytearray(observation["pixels"][0, -1].tobytes())
    scores = [0.0]
    actions = []
    decision = 0
    keys = ("global_feats", "entity_feats", "entity_types", "entity_mask")
    with torch.inference_mode():
        while True:
            guard()
            tensors = [torch.from_numpy(observation[key]).to("mps") for key in keys]
            output = model(*tensors)
            assert bool(torch.isfinite(output.logits).all())
            action = int(output.logits.argmax(dim=-1).item())
            actions.append(action)
            for _ in range(2):
                guard()
                result = env.step(np.array([action], dtype=np.int64))
                observation = result["observations"]
                info = result["info"][0]
                # The wrapper intentionally excludes the terminal image. The
                # final captured image repeats the last valid gameplay frame.
                frames.extend(observation["pixels"][0, -1].tobytes())
                scores.append(info["score"])
                if result["terminated"][0] or result["truncated"][0]:
                    break
            if result["terminated"][0] or result["truncated"][0]:
                break
            decision += 1
            if decision % 100 == 0:
                print(json.dumps({"gameplay_frames": info["gameplay_frames"],
                                  "score": info["score"], "elapsed_seconds": time.monotonic() - START}), flush=True)
            assert torch.mps.driver_allocated_memory() <= PLAN["limits"]["MPS_bytes"]
    for key in ("alive_frames", "gameplay_frames", "score", "score_raw_fixed", "terminated", "truncated", "death_cause", "fatal_gameplay_frame", "death_observed_lethal_contacts", "objective_return"):
        assert info[key] == expected[key], (key, info[key], expected[key])
    assert len(frames) == len(scores) * 16384
    (OUT / "frames.palette.zlib").write_bytes(zlib.compress(frames, 9))
    publish("trace.json", {"scores": scores, "actions_K4": actions})
    publish("result.json", {"status": "passed_exact_recorded_episode_metrics", "training": False,
                            "checkpoint_promoted": False, "episode": info,
                            "frame_count": len(scores), "fps": 30,
                            "wall_seconds": time.monotonic() - START,
                            "RSS_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                            "MPS_driver_bytes": torch.mps.driver_allocated_memory(),
                            "capture_boundary": "post_method;terminal_repeats_last_valid_frame",
                            "frames_sha256": digest(OUT / "frames.palette.zlib")})
    print(json.dumps({"status": "passed", "alive_frames": info["alive_frames"], "score": info["score"]}), flush=True)


publish("execution-started.json", {"pid": os.getpid(), "actual_launch_count": 1,
                                    "monotonic": START, "plan_sha256": digest(OUT / "plan.json")})
try:
    main()
except BaseException as error:
    publish("failure.json", {"error": repr(error), "traceback": traceback.format_exc(),
                             "wall_seconds": time.monotonic() - START})
    raise
