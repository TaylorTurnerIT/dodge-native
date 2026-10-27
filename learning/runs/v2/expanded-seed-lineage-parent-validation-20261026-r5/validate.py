"""Independent CPU checkpoint metadata and conservative seed-envelope check. No environments or training."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parent
ROOT = BASE.parents[2]
CHILD = BASE / "expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


MASK = (1 << 64) - 1
EXCLUDED = ((0xB0000000, 0xB00003E7), (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7))


def mix(x):
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK
    return (x ^ (x >> 31)) & MASK


def seed(run, slot, episode):
    base = mix(run ^ 0x444F4447455F5632) ^ mix((slot + 0x9E3779B97F4A7C15) & MASK) ^ mix((episode + 0xD1B54A32D192ED03) & MASK)
    counter = 0
    while True:
        actual = mix(base ^ mix((counter + 0x94D049BB133111EB) & MASK)) >> 32
        if not any(lo <= actual <= hi for lo, hi in EXCLUDED):
            return counter, actual
        counter += 1


def main():
    manifest = json.loads((CHILD / "manifest.json").read_text())
    files = manifest.get("files", {})
    for name, digest in files.items():
        require(sha(CHILD / name) == digest, "Child output changed: " + name)
    source = CHILD / "reconstruct.py"
    spec = importlib.util.spec_from_file_location("closed_seed_reconstruction", source)
    child = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(child)
    require(sha(ROOT / "crates/dodge-rl-env/src/seed.rs") == child.SEED_SOURCE_SHA256, "Seed source differs")
    import torch
    torch.set_num_threads(2)
    nodes = []
    envelope = set()
    checked_live = 0
    previous = None
    parent_link_records = []
    child_evidence = json.loads((CHILD / "evidence.json").read_text())
    evidence_nodes = {n["name"]: n for n in child_evidence["nodes"]}
    for node in child.NODES:
        path = ROOT / node["checkpoint"]
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == node["sha256"], "Checkpoint byte pin differs")
        state = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=False)
        stored_parent = state.get("parent_checkpoint_sha256")
        link_kind = "checkpoint_payload"
        if stored_parent != previous:
            require(stored_parent is None and previous is not None, "Non-null actual checkpoint parent differs")
            registration_path = ROOT / node["registration"]
            require(sha(registration_path) == evidence_nodes[node["name"]]["registration_sha256"], "Registration changed")
            registration = json.loads(registration_path.read_text())
            parent = registration["parent"]
            require(parent["sha256"] == previous, "Legacy external parent binding differs")
            require(sha(Path(parent["path"])) == previous, "Legacy external parent bytes differ")
            for key in ("validation_receipt", "anchor"):
                path_key, digest_key = key + "_path", key + "_sha256"
                if path_key in parent:
                    require(sha(Path(parent[path_key])) == parent[digest_key], "Legacy parent anchor changed")
            link_kind = "registered_external_parent_anchor;legacy_payload_parent_null"
        parent_link_records.append({"node": node["name"], "stored_parent": stored_parent,
                                    "expected_parent": previous, "proof": link_kind})
        previous = node["sha256"]
        config = state["identity"]["config"]
        run = state.get("run_seed", config.get("phase_settings", {}).get("run_seed"))
        require(run == node["run_seed"], "Actual run seed differs: " + node["name"])
        require(tuple(tuple(pair) for pair in config["excluded_seed_ranges"]) == EXCLUDED, "Actual exclusions differ")
        indices = state["next_episode_indices"]
        require(len(indices) == 64 and all(type(i) is int and i >= 0 for i in indices), "Malformed checkpoint bounds")
        maximum = max(indices)
        # Every slot uses 0..max(next index), inclusive. This is deliberately broader than each actual slot prefix.
        for slot in range(64):
            for episode in range(maximum + 1):
                envelope.add(seed(run, slot, episode)[1])
        live = state.get("abandoned_episodes", [])
        for row in live:
            metadata = row["seed"]
            actual = seed(run, metadata["slot"], metadata["episode"])
            require(actual == (metadata["counter"], metadata["actual_seed"]), "Actual live seed replay differs")
            require(metadata["actual_seed"] in envelope, "Live seed omitted from conservative envelope")
            checked_live += 1
        require(sha(path) == node["sha256"], "Checkpoint changed during CPU read")
        nodes.append({"name": node["name"], "checkpoint_sha256": node["sha256"], "run_seed": run,
                      "minimum_next_episode_index": min(indices), "maximum_next_episode_index": maximum,
                      "all_slot_inclusive_bound": maximum, "live_seed_records_replayed": len(live)})
        del state, raw
    collisions = {name: sorted(value for value in envelope if lo <= value <= hi)
                  for name, (lo, hi) in child.RANGES.items()}
    require(all(not values for values in collisions.values()), "Proposed cohort intersects conservative ancestor envelope")
    receipt = {"schema": "expanded_seed_parent_checkpoint_validation_v1", "status": "passed",
               "child_source_sha256": sha(source), "child_evidence_sha256": sha(CHILD / "evidence.json"),
               "CPU_checkpoint_payloads_read": len(nodes), "parent_links_verified": len(nodes) - 1, "parent_link_records": parent_link_records,
               "actual_run_seeds_and_exclusions_verified": True, "nodes": nodes,
               "live_seed_records_replayed": checked_live, "conservative_unique_seed_count": len(envelope),
               "conservative_seed_set_sha256": hashlib.sha256("\n".join(str(s) for s in sorted(envelope)).encode()).hexdigest(),
               "collisions": collisions, "scope": "Actual training ancestry of the six original retained checkpoints through348; no global workspace nonuse claim.",
               "no_games_or_training_or_MPS": True, "no_shared_or_frozen_input_mutation": True}
    with (OWN / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "passed", "checkpoints": len(nodes), "live_seeds_replayed": checked_live,
                      "conservative_unique_seeds": len(envelope), "collisions": collisions}))


if __name__ == "__main__":
    main()
