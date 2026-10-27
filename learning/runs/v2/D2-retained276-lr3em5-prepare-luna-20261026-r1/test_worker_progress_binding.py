"""CPU regression: execute the extracted worker call against pinned production PPO."""
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "runner.py"
RUNTIME = HERE.parent / "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
sys.path.insert(0, str(RUNTIME))
import torch
from torch import nn
from torch.distributions import Categorical
from dodge_rl.ppo import PPOConfig, RolloutBatch, ppo_update

def worker_call():
    tree = ast.parse(RUNNER.read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "guarded_update"]
    assert len(calls) == 1
    return calls[0]

class TinyTeacher(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Linear(14, 8)
        self.actor_head = nn.Linear(8, 9)
        self.critic_head = nn.Linear(8, 1)
    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        hidden = torch.tanh(self.trunk(global_feats[:, 0]))
        return SimpleNamespace(logits=self.actor_head(hidden), values=self.critic_head(hidden).squeeze(-1))

def make_inputs():
    torch.manual_seed(20261026)
    model = TinyTeacher()
    obs = {"global_feats": torch.randn((1, 1, 1, 14)),
           "entity_feats": torch.zeros((1, 1, 80, 16)),
           "entity_types": torch.zeros((1, 1, 80), dtype=torch.int64),
           "entity_mask": torch.zeros((1, 1, 80), dtype=torch.bool)}
    action = torch.tensor([[0]], dtype=torch.int64)
    with torch.no_grad():
        out = model(*(v.flatten(0, 1) for v in obs.values()))
        old_log_prob = Categorical(logits=out.logits).log_prob(action.flatten()).reshape(1, 1)
        values = out.values.reshape(1, 1)
    batch = RolloutBatch(**obs, actions=action, old_log_probs=old_log_prob, values=values,
                         rewards=torch.tensor([[1.0]]), next_values=values + 0.1,
                         terminated=torch.zeros((1, 1), dtype=torch.bool),
                         truncated=torch.zeros((1, 1), dtype=torch.bool))
    config = PPOConfig(update_epochs=1, minibatch_size=1, target_kl=1e6)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.00003, eps=config.adam_eps)
    return model, optimizer, batch, config

def execute(call, fail_after_step):
    model, optimizer, batch, config = make_inputs()
    progress = {"complete": True, "in_update": False, "completed_updates": 0}
    class Guard:
        def check(self):
            if fail_after_step and any(float(state.get("step", 0)) == 1 for state in optimizer.state.values()):
                raise RuntimeError("injected resource failure after optimizer step 1")
    class Transition:
        @staticmethod
        def guarded_update(optimizer, expected_lr, update_fn, *args, **kwargs):
            assert all(group["lr"] == expected_lr for group in optimizer.param_groups)
            value = update_fn(*args, **kwargs)
            assert all(group["lr"] == expected_lr for group in optimizer.param_groups)
            return value
    namespace = {"ppo_update": ppo_update, "model": model, "optimizer": optimizer,
                 "collection": SimpleNamespace(batch=batch), "ppo": config,
                 "guard": Guard(), "progress": progress, "transition_helper":Transition}
    try:
        eval(compile(ast.Expression(call), str(RUNNER), "eval"), namespace)
    except RuntimeError as exc:
        assert str(exc) == "injected resource failure after optimizer step 1"
        assert all(state["step"].item() == 1 for state in optimizer.state.values())
        return progress
    progress["completed_updates"] = 1
    return progress

def main():
    call = worker_call()
    assert call.args[2].id == "ppo_update" and call.args[1].value == 0.00003
    assert any(k.arg == "progress" and isinstance(k.value, ast.Name) and k.value.id == "progress"
               for k in call.keywords), "worker PPO call must bind progress=progress"
    failed = execute(call, True)
    assert failed["optimizer_steps"] == 1 and failed["complete"] is False and failed["in_update"] is True
    assert failed["completed_updates"] == 0 and failed["state"] == "in_update"
    missing = ast.Call(func=call.func, args=call.args,
                       keywords=[k for k in call.keywords if k.arg != "progress"])
    ast.copy_location(missing, call)
    negative = execute(missing, True)
    assert negative["complete"] is True and negative["in_update"] is False
    assert negative["completed_updates"] == 0
    success = execute(call, False)
    assert success["complete"] is True and success["in_update"] is False
    assert success["completed_updates"] == 1 and success["optimizer_steps"] == 1
    print(json.dumps({"status": "passed", "worker_call_ast": "extracted_and_compiled_from_runner.py",
                      "ppo_implementation": "pinned_isolated_runtime_cpu", "failure_with_binding": failed,
                      "failure_missing_binding": negative, "successful_boundary": success,
                      "synthetic_optimizer_steps": 3, "environment_constructed": False,
                      "mps_used": False}, sort_keys=True))

if __name__ == "__main__":
    main()
