"""CPU-only proof of the runner's missing PPO progress binding."""
import ast
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
SOURCE = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r1/runner.py"
sys.path.insert(0, str(RUNTIME))
import torch
from dodge_rl.ppo import ppo_update, PPOConfig

spec = importlib.util.spec_from_file_location("_parent_ppo_fixture", ROOT / "python/tests/test_ppo.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
calls = [node for node in ast.walk(ast.parse(SOURCE.read_text()))
         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ppo_update"]
assert len(calls) == 1 and "progress" not in [keyword.arg for keyword in calls[0].keywords]
torch.set_num_threads(1)
torch.manual_seed(20261026)
results = []
for bind in (False, True):
    model = fixture.TinyTeacher()
    batch = fixture.synthetic_batch(model)
    config = PPOConfig(minibatch_size=5)
    optimizer = fixture.optimizer_for(model, config)
    progress = {"complete": True, "in_update": False, "completed_updates": 0}
    def guard():
        if optimizer.state and max(int(state["step"].item()) for state in optimizer.state.values()) == 1:
            raise RuntimeError("injected failure after first optimizer step")
    try:
        ppo_update(model, optimizer, batch, config, check_guard=guard,
                   **({"progress": progress} if bind else {}))
    except RuntimeError as error:
        assert str(error) == "injected failure after first optimizer step"
    else:
        raise AssertionError("Injected failure did not fire")
    steps = sorted(set(int(state["step"].item()) for state in optimizer.state.values()))
    assert steps == [1]
    results.append({"progress_bound": bind, "actual_optimizer_steps": 1, "reported_progress": progress})
assert results[0]["reported_progress"]["complete"] is True
assert results[1]["reported_progress"]["complete"] is False
assert results[1]["reported_progress"]["optimizer_steps"] == 1
report = {"status": "defect_reproduced", "runner_call_line": calls[0].lineno,
          "finding": "Missing progress=progress loses partial-update accounting on PPO failure; successful runs unaffected.",
          "controls": results, "real_game_episodes": 0, "mps_operations": 0,
          "synthetic_optimizer_steps": 2, "actual_campaigns": 0}
(HERE / "progress-finding.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
