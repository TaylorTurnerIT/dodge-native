"""Validate restored optimizer settings and RNG reads; no environment or updates."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
PREP = Path(__file__).resolve().parent
RUNNER = ROOT / "learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r5"
OLD_PREP = ROOT / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1"


def main():
    started = time.monotonic()
    sys.path.insert(0, str(RUNNER))
    import runner
    registration = runner.read(OLD_PREP / "registration-r2.json")
    runner.verify_pins(registration["pins"])
    sys.path.insert(0, registration["runtime_root"])
    import torch
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher
    torch.set_num_threads(4)
    state = ckpt.load_checkpoint(Path(registration["parent"]["path"]),
                                 expected_sha256=runner.PARENT_SHA)
    expected = {"lr": runner.PPO["learning_rate"], "eps": runner.PPO["adam_eps"],
                "betas": (0.9, 0.999), "weight_decay": 0, "amsgrad": False,
                "maximize": False, "capturable": False, "differentiable": False}
    for group in state["optimizer"]["param_groups"]:
        runner.need(all(group[key] == value for key, value in expected.items()),
                    "Saved optimizer settings differ from registered settings")
    model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=runner.PPO["learning_rate"],
                                 eps=runner.PPO["adam_eps"])
    ckpt.restore_learner(state, model, optimizer, "mps")
    for group in optimizer.param_groups:
        runner.need(all(group[key] == value for key, value in expected.items()),
                    "Restored optimizer settings differ")
    first = ckpt.capture_rng("mps")
    second = ckpt.capture_rng("mps")
    comparisons = {
        "model": runner.fingerprint(model.state_dict()) == runner.fingerprint(state["model"]),
        "Adam": runner.fingerprint(optimizer.state_dict()) == runner.fingerprint(state["optimizer"]),
        "RNG": runner.fingerprint(first) == runner.fingerprint(state["rng"]),
        "repeated_RNG_capture": runner.fingerprint(first) == runner.fingerprint(second),
    }
    runner.need(all(comparisons.values()), "Restoration or repeat RNG capture differs")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mps = torch.mps.driver_allocated_memory()
    elapsed = time.monotonic() - started
    runner.need(elapsed < 120 and rss <= 6442450944 and mps <= 6442450944,
                "Validation resource budget exceeded")
    runner.save(PREP / "restoration-validation-final.json", {
        "status": "passed", "comparisons": comparisons,
        "saved_and_restored_optimizer_settings": expected,
        "all_original_input_pins_checked": len(registration["pins"]),
        "elapsed_seconds": elapsed, "observed_peak_rss_bytes": rss,
        "observed_mps_driver_bytes": mps,
        "parent_sha256": runner.PARENT_SHA,
        "runner_sha256": runner.sha(RUNNER / "runner.py"),
        "validation_script_sha256": runner.sha(Path(__file__)),
        "environment_created": False, "gradients_or_updates": False,
    })
    print(json.dumps({"status": "passed", "comparisons": comparisons,
                      "elapsed_seconds": elapsed}))


if __name__ == "__main__":
    main()
