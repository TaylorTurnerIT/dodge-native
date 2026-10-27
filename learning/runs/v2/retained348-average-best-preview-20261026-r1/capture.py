"""Replay the frozen dev evaluation unchanged; record palette images for two selected episodes."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback
import zlib

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
PLAN = json.loads((OWN / "plan.json").read_text())
START = time.monotonic()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    with (OWN / name).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def guard():
    state = json.loads(Path(PLAN["state_path"]).read_text())
    if state.get("active_inference_diagnostic") != PLAN["expected_lease"] or state.get("active_long_campaign") is not None:
        raise RuntimeError("Preview lease changed or training started")
    if time.monotonic() - START > 170:
        raise RuntimeError("Preview wall budget exceeded")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 6442450944:
        raise RuntimeError("Preview RSS cap exceeded")
    if "torch" in sys.modules and sys.modules["torch"].mps.driver_allocated_memory() > 6442450944:
        raise RuntimeError("Preview MPS driver cap exceeded")


def main():
    guard()
    for relative, digest in PLAN["runtime_files"].items():
        if sha(OWN / relative) != digest:
            raise ValueError("Copied runtime changed: " + relative)
    if sha(PLAN["checkpoint"]) != PLAN["checkpoint_sha256"] or sha(PLAN["certificate"]) != PLAN["certificate_sha256"]:
        raise ValueError("Checkpoint or certificate changed")
    sys.path.insert(0, str(OWN / "runtime"))
    import torch
    from dodge_rl import VecDodgeEnv
    from dodge_rl.checkpoints import load_checkpoint
    from dodge_rl.dev_eval import evaluate
    from dodge_rl.models import OmniscientEntityTeacher
    torch.set_num_threads(4)
    if not torch.backends.mps.is_available():
        raise RuntimeError("Registered MPS replay backend unavailable")
    state = load_checkpoint(Path(PLAN["checkpoint"]), expected_sha256=PLAN["checkpoint_sha256"])
    model = OmniscientEntityTeacher().to("mps")
    model.load_state_dict(state["model"], strict=True)
    model.eval()
    selected = {item["row"]["seed"]: item["role"] for item in PLAN["clips"]}
    captures = {role: {"pixels": bytearray(), "frames": [], "scores": []} for role in selected.values()}

    class RecordingEnv:
        def __init__(self, **kwargs):
            seed = kwargs["seeds_by_slot"][0][0]
            self.role = selected.get(seed)
            kwargs["render_pixels"] = self.role is not None
            self.env = VecDodgeEnv(**kwargs)

        def episode_info(self):
            return self.env.episode_info()

        def observations(self):
            observation = self.env.observations()
            if self.role:
                capture = captures[self.role]
                capture["pixels"].extend(observation["pixels"][0, -1].tobytes())
                capture["frames"].append(0)
                capture["scores"].append(0)
            return observation

        def step(self, actions):
            result = self.env.step(actions)
            if self.role:
                capture = captures[self.role]
                info = result["info"][0]
                capture["pixels"].extend(result["observations"]["pixels"][0, -1].tobytes())
                capture["frames"].append(info["gameplay_frames"])
                capture["scores"].append(info["score"])
            return result

    # Original batching, argmax, K=4, reset and accounting logic remain in the byte-pinned evaluator.
    replay = evaluate(model, "D2", "mps", check_guard=guard, env_factory=RecordingEnv)
    expected = json.loads(Path(PLAN["certificate"]).read_text())["evaluation"]
    if replay["rows"] != expected["rows"]:
        differences = [i for i, (a, b) in enumerate(zip(replay["rows"], expected["rows"])) if a != b]
        raise ValueError("Replay rows differ from recorded evaluation: " + repr(differences))
    for key, value in model.state_dict().items():
        if not torch.equal(value.detach().cpu(), state["model"][key]):
            raise ValueError("Inference changed model state: " + key)
    if any(parameter.grad is not None for parameter in model.parameters()):
        raise ValueError("Inference created gradients")
    for role, capture in captures.items():
        if len(capture["pixels"]) != len(capture["frames"]) * 16384:
            raise ValueError("Palette capture size differs")
        with (OWN / (role + ".palette.zlib")).open("xb") as stream:
            stream.write(zlib.compress(capture.pop("pixels"), 9))
        write(role + ".trace.json", capture)
    guard()
    write("result.json", {"status": "passed_exact_64_recorded_rows", "clips": PLAN["clips"],
                          "wall_seconds": time.monotonic() - START,
                          "RSS_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          "MPS_driver_bytes": torch.mps.driver_allocated_memory(),
                          "mean_alive_frames": replay["mean_alive_frames"], "training": False,
                          "capture": "native palette; K4 snapshots at 15FPS; terminal repeats last valid image"})
    print(json.dumps({"status": "passed", "rows_matched": 64, "clips": 2, "elapsed": time.monotonic() - START}), flush=True)


write("execution-started.json", {"pid": os.getpid(), "launch_count": 1, "plan_sha256": sha(OWN / "plan.json")})
try:
    main()
except BaseException as error:
    write("failure.json", {"error": repr(error), "traceback": traceback.format_exc()})
    raise
