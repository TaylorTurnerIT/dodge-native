"""Write the learned physics (potential network + damping) as JSON for the Rust planner."""
import json, sys
from pathlib import Path
import torch
sys.path.insert(0, str(Path(__file__).parent))
import physics

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "physics.pt"
target = Path(sys.argv[2]) if len(sys.argv) > 2 else source.with_suffix(".json")
model = physics.Physics()
model.load_state_dict(torch.load(source))
layers = [m for m in model.potential if isinstance(m, torch.nn.Linear)]
spec = {
    "layers": [{"weights": l.weight.detach().double().tolist(), "bias": l.bias.detach().double().tolist()} for l in layers],
    "gamma": float(model.gamma),
}
target.write_text(json.dumps(spec))
print("wrote", target, "gamma", spec["gamma"])
