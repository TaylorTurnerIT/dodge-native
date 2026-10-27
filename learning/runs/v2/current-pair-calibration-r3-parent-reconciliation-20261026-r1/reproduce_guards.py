"""CPU-only reproduction of the repeated-evaluation guard-count defect."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R3 = ROOT / "learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r3"
R6 = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6"
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def main():
    sys.path.insert(0, str(RUNTIME))
    import torch
    from dodge_rl.dev_eval import development_environment_config
    worker = load("_parent_r3_guard_worker", R6 / "worker.py")
    probe = load("_parent_r3_guard_probe", R3 / "probe.py")
    paths = [R6 / "worker.py", R6 / "paired_eval.py", R3 / "probe.py"]
    before = {str(path): digest(path) for path in paths}
    class CpuModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)
            self.calls = 0
        def forward(self, global_feats, *unused):
            self.calls += 1
            return type("Output", (), {"logits": torch.zeros((global_feats.shape[0], 9)) + self.anchor})()
    model = CpuModel().eval()
    guards = []
    passes = []
    for _ in range(2):
        start = len(guards)
        rows = worker.evaluate(model, checkpoint="best204", mode="argmax", replicate_seed=None,
                               env_factory=probe.SyntheticEnv,
                               config_factory=development_environment_config,
                               expected_control_path=None, check_guard=lambda: guards.append(1),
                               fixture=False)
        passes.append({"guards": len(guards) - start, "synthetic_rows": len(rows)})
    assert [p["guards"] for p in passes] == [136, 136]
    assert len(guards) == 272 and model.calls == 16
    common = dict(gaps=[0.25], after_read_ages=[0.1], sample_count=20,
                  forward_count=240, evaluate_passes=2, active_seconds=30.0)
    # The unrelated workload metrics are fabricated to isolate only this predicate.
    try:
        probe.validate_representative_measurements(guard_count=len(guards), **common)
    except RuntimeError as error:
        actual_rejected = str(error)
    else:
        raise AssertionError("Expected frozen R3 to reject the real repeated-pass count")
    probe.validate_representative_measurements(guard_count=208, **common)
    after = {str(path): digest(path) for path in paths}
    assert before == after
    report = {"status": "defect_reproduced", "passes": passes, "actual_total_guards": len(guards),
              "actual_cpu_forwards": model.calls, "real_game_episodes": 0, "mps_operations": 0,
              "expected_formula": "136 * evaluate_passes", "frozen_r3_formula": "64 + 72 * evaluate_passes",
              "frozen_validator_rejects_actual": actual_rejected,
              "frozen_validator_accepts_incorrect_208": True,
              "validator_other_metrics_fabricated_to_isolate_guard_predicate": True,
              "source_before": before, "source_after": after}
    (HERE / "guard-reproduction.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

if __name__ == "__main__":
    main()
