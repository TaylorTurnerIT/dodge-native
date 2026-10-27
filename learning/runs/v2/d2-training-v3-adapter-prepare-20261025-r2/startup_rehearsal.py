"""Explicit startup-only checkpoint restoration rehearsal; never creates an environment."""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import helper

ROOT = Path(__file__).resolve().parents[4]
PREP = Path(__file__).resolve().parent
EVIDENCE = ROOT / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1"
RUNTIME = EVIDENCE / "runtime"
PYTHON = ROOT / "python/.venv/bin/python"
PARENT = ROOT / "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt"
NATIVE = RUNTIME / "dodge_rl/_native.cpython-312-darwin.so"
OLD_NATIVE = ROOT / "python/dodge_rl/_native.cpython-312-darwin.so"
EXPECTED_PARENT = helper.PARENT_SHA
EXPECTED_NATIVE = helper.NEW_NATIVE_SHA
EXPECTED_OLD_NATIVE = helper.OLD_NATIVE_SHA


def main():
    started = time.monotonic()
    samples = []
    sys.path.insert(0, str(RUNTIME))
    import numpy as np
    import torch
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    source = {"helper.py": helper.sha(PREP / "helper.py"),
              "worker.py": helper.sha(PREP / "worker.py"),
              "adapter.py": helper.sha(PREP / "adapter.py"),
              "launcher.py": helper.sha(PREP / "launcher.py"),
              "test_adapter.py": helper.sha(PREP / "test_adapter.py"),
              "test_launcher.py": helper.sha(PREP / "test_launcher.py"),
              "startup_rehearsal.py": helper.sha(PREP / "startup_rehearsal.py"),
              "parent_checkpoint": helper.sha(PARENT), "new_native": helper.sha(NATIVE),
              "old_native": helper.sha(OLD_NATIVE)}
    if source["parent_checkpoint"] != EXPECTED_PARENT or source["new_native"] != EXPECTED_NATIVE or source["old_native"] != EXPECTED_OLD_NATIVE:
        raise RuntimeError("Pinned checkpoint or native extension hash changed")
    if PYTHON.resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Rehearsal interpreter differs: " + sys.executable)
    torch.set_num_threads(4)
    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS unavailable")
    parent = ckpt.load_checkpoint(PARENT, expected_sha256=EXPECTED_PARENT)
    ckpt.require_complete_update(parent)
    def sample(stage):
        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        samples.append({"stage": stage, "elapsed_seconds": time.monotonic() - started,
                        "observed_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
                        "observed_mps_driver_bytes": int(torch.mps.driver_allocated_memory())})
    sample("checkpoint_loaded")
    model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
    if model.architecture_description() != parent["identity"]["architecture"]:
        raise RuntimeError("Teacher architecture differs")
    optimizer = torch.optim.Adam(model.parameters(), lr=helper.PPO["learning_rate"], eps=helper.PPO["adam_eps"])
    ckpt.restore_learner(parent, model, optimizer, "mps")
    sample("learner_restored")
    restored = {"model": model.state_dict(), "Adam": optimizer.state_dict(), "RNG": ckpt.capture_rng("mps")}
    expected = {"model": parent["model"], "Adam": parent["optimizer"], "RNG": parent["rng"]}
    comparisons = {name: {"matched": helper.fingerprint(restored[name]) == helper.fingerprint(expected[name]),
                          "restored_sha256": helper.fingerprint(restored[name]),
                          "expected_sha256": helper.fingerprint(expected[name]),
                          "mismatch_paths": helper.mismatch_paths(restored[name], expected[name])}
                   for name in restored}
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    evidence = {"status": "passed" if all(item["matched"] for item in comparisons.values()) else "failed",
                "startup_only": True, "environment_created": False, "gradients_or_updates": False,
                "checkpoint_sha256": EXPECTED_PARENT, "native_sha256": EXPECTED_NATIVE,
                "old_native_sha256": EXPECTED_OLD_NATIVE, "source_sha256": source,
                "runtime": {"python": sys.version.split()[0], "torch": str(torch.__version__),
                            "numpy": str(np.__version__), "interpreter": str(PYTHON)},
                "comparisons": comparisons, "elapsed_seconds": time.monotonic() - started,
                "observed_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
                "observed_mps_driver_bytes": int(torch.mps.driver_allocated_memory()),
                "resource_samples": samples}
    (PREP / "startup-rehearsal-result.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": evidence["status"], "elapsed_seconds": evidence["elapsed_seconds"],
                      "comparisons": comparisons}, sort_keys=True))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
