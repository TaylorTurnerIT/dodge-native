"""CPU/stdlib-only microbenchmarks of host-side costs present in the baseline run.

No model, environment, checkpoint, or MPS use. Inputs are synthetic tensors with
the rollout's exact shapes/dtypes and one saved EpisodeInfo row copied 64 times.
Usage: python -I host_microbench.py <training-events.jsonl> <scratch_dir>
"""
import copy, json, os, sys, time
import torch
from torch.distributions import Categorical

torch.set_num_threads(2)
events, scratch = sys.argv[1], sys.argv[2]
out = {}

def bench(fn, n):
    fn(); t = time.perf_counter()
    for _ in range(n): fn()
    return (time.perf_counter() - t) / n

# 1. Host deepcopy of one step's 64 EpisodeInfo rows (collection does >=4/step).
with open(events) as f:
    for line in f:
        e = json.loads(line)
        if e["kind"] == "completion":
            info = e["native_info"]; break
infos = [copy.deepcopy(info) for _ in range(64)]
out["deepcopy_64_infos_ms"] = 1e3 * bench(lambda: copy.deepcopy(infos), 300)

# 2. Durable per-step event write: json + write + flush + fsync (worker.emit).
path = os.path.join(scratch, "fsync-scratch.jsonl")
row = {"kind": "returned_step_cost", "update": 1, "decision": 0, "elapsed_raw_frames": [4] * 64}
with open(path, "w") as s:
    def emit():
        s.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n"); s.flush(); os.fsync(s.fileno())
    out["emit_fsync_ms"] = 1e3 * bench(emit, 300)
os.remove(path)

# 3. PPO host gather + per-minibatch CPU copies (baseline: 4 epochs x 32 minibatches).
N = 16384
flat = dict(global_feats=torch.randn(N, 1, 14), entity_feats=torch.randn(N, 80, 16),
            entity_types=torch.randint(0, 9, (N, 80)), entity_mask=torch.rand(N, 80) > .5)
g = torch.Generator().manual_seed(0)
def gather_epoch():
    order = torch.randperm(N, generator=g)
    for s in range(0, N, 512):
        idx = order[s:s + 512]
        _ = {k: v[idx] for k, v in flat.items()}
out["cpu_gather_one_epoch_ms"] = 1e3 * bench(gather_epoch, 5)
out["rollout_obs_bytes"] = sum(v.numel() * v.element_size() for v in flat.values())

# 4. Categorical validation overhead (CPU; MPS adds a device sync per check).
logits = torch.randn(512, 9); a = torch.randint(0, 9, (512,))
v_on = bench(lambda: Categorical(logits=logits).log_prob(a), 2000)
v_off = bench(lambda: Categorical(logits=logits, validate_args=False).log_prob(a), 2000)
out["categorical_validated_us"] = 1e6 * v_on
out["categorical_unvalidated_us"] = 1e6 * v_off
same = torch.equal(Categorical(logits=logits).log_prob(a), Categorical(logits=logits, validate_args=False).log_prob(a))
out["categorical_logprob_bitwise_equal"] = same
print(json.dumps(out, indent=2, sort_keys=True))
