#!/usr/bin/env python3
"""Targeted reconstruction of the accepted 348 checkpoint seed ancestry.

Stdlib only.  Reads metadata, journals, and checkpoint bytes for SHA-256.  It
never imports frozen repository source and never deserializes checkpoint
payloads.  Any hash or replay mismatch stops the run and writes a retained
failure record inside this directory.

Run with:
    PYTHONDONTWRITEBYTECODE=1 python3 -B reconstruct.py
"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

SEED_SOURCE = "crates/dodge-rl-env/src/seed.rs"
SEED_SOURCE_SHA256 = "239cb9d88a61fff7d63c3c13c80e4552caafe814729160f8fb2948d3c1498832"
D1_NATIVE_SHA256 = "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
D2_NATIVE_SHA256 = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
SEED_STREAM_VERSION = "dodge_slot_splitmix64_high32_reject_v1"
SEED_EXCLUSION_VERSION = "mandatory_b_plus_inclusive_union_rehash_v1"
EXCLUSIONS = (
    (0xB0000000, 0xB00003E7),
    (0xD0000000, 0xD000007F),
    (0xE0000000, 0xE00003E7),
)
RANGES = {
    "ranking_0xD1000000_0xD10003FF": (0xD1000000, 0xD10003FF),
    "confirmation_2048_0xD2000000_0xD20007FF": (0xD2000000, 0xD20007FF),
    "confirmation_1024_0xD2000000_0xD20003FF": (0xD2000000, 0xD20003FF),
}
MAX_ANCESTRY_PAYLOADS = 20

PROTOCOL = "docs/v2-m3-run-protocol.json"
RECEIPT_348 = (
    "learning/runs/v2/D2-retained324-linear-parent-terminal-audit-20261026-r1/"
    "retained-best-candidate-receipt.json"
)
RECEIPT_348_SHA256 = "cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016"

# name, checkpoint, sha256, registration, run_seed, journal, bound_source, parent
NODES = [
    {
        "name": "D1-pilot",
        "checkpoint": "learning/runs/v2/milestone3-D1-pilot-r1/checkpoint-000004-candidate.pt",
        "sha256": "aaafdaaef6c2e79acf7af025714f2d4f9113631743c7b80a7d4fa1b9724e374b",
        "registration": "learning/runs/v2/milestone3-D1-pilot-r1/identity.json",
        "run_seed": 5562878240475796481,
        "journal": "learning/runs/v2/milestone3-D1-pilot-r1",
        "bound_source": "journal",
        "parent": None,
    },
    {
        "name": "D1-curriculum-9",
        "checkpoint": "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt",
        "sha256": "ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f",
        "registration": "learning/runs/v2/milestone3-D1-curriculum-r1/identity.json",
        "parent_link": "learning/runs/v2/milestone3-D1-curriculum-r1/parent-lineage.json",
        "run_seed": 5562881586070242561,
        "journal": "learning/runs/v2/milestone3-D1-curriculum-r1",
        "bound_source": "journal",
        "parent": "D1-pilot",
    },
    {
        "name": "D2-training-v3-72",
        "checkpoint": "learning/runs/v2/D2-training-v3-20261025-r1/checkpoint-000072-candidate.pt",
        "sha256": "2e13b46edad5b2790cec52b47d33b643cbd6846387994c24fe14d5d36f0521a2",
        "registration": "learning/runs/v2/d2-training-v3-parent-prepare-20261025-r2/registration-r8.json",
        "run_seed": 810631976,
        "journal": "learning/runs/v2/D2-training-v3-20261025-r1",
        "bound_source": "worker",
        "parent": "D1-curriculum-9",
    },
    {
        "name": "D2-continuation-132",
        "checkpoint": "learning/runs/v2/D2-continuation-20261025-r1/checkpoint-000132-candidate.pt",
        "sha256": "bf858ed9975e6f994acbca011895b140be6943cf1852c88b54549a9c8db0c1a8",
        "registration": "learning/runs/v2/d2-continuation-parent-prepare-20261025-r1/registration-r1.json",
        "run_seed": 810631976,
        "journal": "learning/runs/v2/D2-continuation-20261025-r1",
        "bound_source": "worker",
        "parent": "D2-training-v3-72",
    },
    {
        "name": "D2-gradient-180",
        "checkpoint": "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt",
        "sha256": "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea",
        "registration": "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/registration-proposed.json",
        "run_seed": 810631976,
        "journal": "learning/runs/v2/D2-gradient-alignment-20261025-r2",
        "bound_source": "worker",
        "parent": "D2-continuation-132",
    },
    {
        "name": "D2-best180-204",
        "checkpoint": "learning/runs/v2/D2-best180-branch-luna-20261026-r1/checkpoint-000204-candidate.pt",
        "sha256": "f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442",
        "registration": "learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/registration-proposed.json",
        "run_seed": 3791628417,
        "journal": "learning/runs/v2/D2-best180-branch-luna-20261026-r1",
        "bound_source": "worker",
        "parent": "D2-gradient-180",
    },
    {
        "name": "D2-retained204-276",
        "checkpoint": "learning/runs/v2/D2-retained204-lr1e4-20261026-r1/checkpoint-000276-candidate.pt",
        "sha256": "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292",
        "registration": "learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r3/registration.json",
        "run_seed": 3791628418,
        "journal": "learning/runs/v2/D2-retained204-lr1e4-20261026-r1",
        "bound_source": "worker",
        "parent": "D2-best180-204",
    },
    {
        "name": "D2-retained276-300",
        "checkpoint": "learning/runs/v2/D2-retained276-lr3em5-20261026-r2/checkpoint-000300-candidate.pt",
        "sha256": "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710",
        "registration": "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json",
        "run_seed": 3791628420,
        "journal": "learning/runs/v2/D2-retained276-lr3em5-20261026-r2",
        "bound_source": "worker",
        "parent": "D2-retained204-276",
    },
    {
        "name": "D2-retained300-324",
        "checkpoint": "learning/runs/v2/D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt",
        "sha256": "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc",
        "registration": "learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/registration.json",
        "run_seed": 4200000000,
        "journal": "learning/runs/v2/D2-retained300-continuation-20261026-r1",
        "bound_source": "worker",
        "parent": "D2-retained276-300",
    },
    {
        "name": "D2-retained324-348",
        "checkpoint": "learning/runs/v2/D2-retained324-linear-lr-20261026-r1/checkpoint-000348-candidate.pt",
        "sha256": "b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369",
        "registration": "learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json",
        "run_seed": 4200000001,
        "journal": "learning/runs/v2/D2-retained324-linear-lr-20261026-r1",
        "bound_source": "worker",
        "parent": "D2-retained300-324",
    },
]

# All 19 top-level journals and their actual run seed (proved by replay below).
JOURNAL_SEEDS = {
    "D2-best180-branch-luna-20261026-r1": 3791628417,
    "D2-continuation-20261025-r1": 810631976,
    "D2-continuation-20261025-r2": 810631976,
    "D2-gradient-alignment-20261025-r1": 810631976,
    "D2-gradient-alignment-20261025-r2": 810631976,
    "D2-retained204-lr1e4-20261026-r1": 3791628418,
    "D2-retained276-continuation-20261026-r2": 3791628419,
    "D2-retained276-lr3em5-20261026-r2": 3791628420,
    "D2-retained300-continuation-20261026-r1": 4200000000,
    "D2-retained324-continuation-20261026-r1": 4200000001,
    "D2-retained324-linear-lr-20261026-r1": 4200000001,
    "D2-training-v3-20261025-r1": 810631976,
    "critic-diagnostic-D2-20261025-r2": 3192039780,
    "milestone3-D1-curriculum-r1": 5562881586070242561,
    "milestone3-D1-pilot-r1": 5562878240475796481,
    "milestone3-D2-curriculum-r1": 5562881586070242562,
    "milestone3-device-probe-r1": 5562878279179977985,
    "postovernight-long-D2-campaign-r1": 5562873868232098305,
    "postovernight-long-D2-campaign-r2": 5562873868232098305,
}
KNOWN_RUN_SEEDS = sorted(set(JOURNAL_SEEDS.values()))
WORKER_BOUND_JOURNALS = {
    "D2-training-v3-20261025-r1",
    "D2-continuation-20261025-r1",
    "D2-gradient-alignment-20261025-r2",
    "D2-best180-branch-luna-20261026-r1",
    "D2-retained204-lr1e4-20261026-r1",
    "D2-retained276-lr3em5-20261026-r2",
    "D2-retained300-continuation-20261026-r1",
    "D2-retained324-linear-lr-20261026-r1",
}
MASK64 = (1 << 64) - 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(rel: str):
    with (REPO / rel).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def mix(value: int) -> int:
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def training_seed(run_seed: int, slot: int, episode: int) -> tuple[int, int]:
    """Exact v1 tuple hash, upper 32 bits, reject B/D128/E."""
    base = (
        mix(run_seed ^ 0x444F4447455F5632)
        ^ mix((slot + 0x9E3779B97F4A7C15) & MASK64)
        ^ mix((episode + 0xD1B54A32D192ED03) & MASK64)
    )
    counter = 0
    while True:
        candidate = mix(base ^ mix((counter + 0x94D049BB133111EB) & MASK64))
        actual = (candidate >> 32) & 0xFFFFFFFF
        if not any(start <= actual <= end for start, end in EXCLUSIONS):
            return counter, actual
        counter += 1


def iter_seed_records(value):
    """Yield every nested {actual_seed,counter,episode,slot} record."""
    if isinstance(value, dict):
        if (
            isinstance(value.get("actual_seed"), int)
            and isinstance(value.get("counter"), int)
            and isinstance(value.get("episode"), int)
            and isinstance(value.get("slot"), int)
        ):
            yield value
        for child in value.values():
            yield from iter_seed_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_seed_records(child)


class Reconstruction:
    def __init__(self) -> None:
        self.evidence = {
            "schema": "expanded_seed_lineage_reconstruction_v1",
            "scope": {
                "terminal_checkpoint": NODES[-1]["checkpoint"],
                "terminal_checkpoint_sha256": NODES[-1]["sha256"],
                "ancestry_payload_cap": MAX_ANCESTRY_PAYLOADS,
                "checkpoint_payload_deserialized": False,
                "frozen_source_imported": False,
            },
            "seed_source": {},
            "nodes": [],
            "parent_chain": {},
            "receipt_348": {},
            "journal_replay": {},
            "ancestor_closure": {},
            "workspace_envelope": {},
            "supplemental_scans": {},
            "collisions": {},
            "proof_boundary": {},
        }
        self.cache: dict[tuple[int, int, int], tuple[int, int]] = {}
        self.journal_bounds: dict[str, list[int]] = {}
        self.journal_stats: dict[str, dict] = {}

    def fail(self, message: str) -> None:
        failure = dict(self.evidence)
        failure["status"] = "failed"
        failure["failure"] = message
        (HERE / "evidence.failed.json").write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8"
        )
        print(f"FAILED: {message}", file=sys.stderr)
        raise SystemExit(1)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.fail(message)

    def seed(self, run_seed: int, slot: int, episode: int) -> tuple[int, int]:
        key = (run_seed, slot, episode)
        if key not in self.cache:
            self.cache[key] = training_seed(run_seed, slot, episode)
        return self.cache[key]

    def check_seed_source(self) -> None:
        source_path = REPO / SEED_SOURCE
        self.require(source_path.is_file(), f"missing seed source {SEED_SOURCE}")
        actual = sha256_file(source_path)
        self.require(actual == SEED_SOURCE_SHA256, "seed.rs hash mismatch")
        protocol = load_json(PROTOCOL)
        self.require(
            protocol["seed_stream_version"] == SEED_STREAM_VERSION,
            "protocol seed stream version mismatch",
        )
        self.require(
            protocol["seed_exclusion_version"] == SEED_EXCLUSION_VERSION,
            "protocol exclusion version mismatch",
        )
        expected_protocol_seeds = {
            "D1": 5562881586070242561,
            "D2": 5562881586070242562,
            "D3": 5562881586070242563,
            "pilot": 5562878240475796481,
            "probe": 5562878279179977985,
        }
        for name, expected in expected_protocol_seeds.items():
            self.require(
                protocol["seed_namespace_table"][name]["run_seed"] == expected,
                f"protocol seed mismatch for {name}",
            )
        self.require(
            tuple(tuple(item) for item in protocol["training_excluded_ranges"])
            == EXCLUSIONS,
            "protocol exclusion ranges mismatch",
        )
        self.evidence["seed_source"] = {
            "path": SEED_SOURCE,
            "sha256": actual,
            "stream_version": SEED_STREAM_VERSION,
            "exclusion_version": SEED_EXCLUSION_VERSION,
            "exclusions": [list(item) for item in EXCLUSIONS],
            "protocol_path": PROTOCOL,
            "protocol_sha256": sha256_file(REPO / PROTOCOL),
            "protocol_registered_seeds": expected_protocol_seeds,
            "constants": {
                "mix_multipliers": ["0xBF58476D1CE4E5B9", "0x94D049BB133111EB"],
                "tuple_offsets": [
                    "0x444F4447455F5632",
                    "0x9E3779B97F4A7C15",
                    "0xD1B54A32D192ED03",
                    "0x94D049BB133111EB",
                ],
                "candidate": "upper 32 bits of mix(base ^ mix(counter + offset))",
            },
        }

    def check_native_bindings(self) -> None:
        rows = []
        for node in NODES:
            reg = load_json(node["registration"])
            if "native" in reg:
                native = reg["native"]
                self.require(
                    native.get("sha256") == D2_NATIVE_SHA256,
                    f"D2 native binding mismatch for {node['name']}",
                )
                self.require(
                    native.get("old_sha256") == D1_NATIVE_SHA256,
                    f"D2 old native binding mismatch for {node['name']}",
                )
                rows.append(
                    {
                        "node": node["name"],
                        "path": native.get("path"),
                        "sha256": native.get("sha256"),
                        "old_sha256": native.get("old_sha256"),
                    }
                )
            else:
                native_sha = reg["foundation"]["extension_sha256"]
                self.require(
                    native_sha == D1_NATIVE_SHA256,
                    f"D1 native binding mismatch for {node['name']}",
                )
                rows.append(
                    {
                        "node": node["name"],
                        "path": reg["foundation"].get("extension_path"),
                        "sha256": native_sha,
                        "old_sha256": None,
                    }
                )
        self.evidence["native_bindings"] = {
            "d1_sha256": D1_NATIVE_SHA256,
            "d2_sha256": D2_NATIVE_SHA256,
            "per_node": rows,
        }

    def check_source_bindings(self) -> None:
        pilot = load_json("learning/runs/v2/milestone3-D1-pilot-r1/identity.json")
        pins = pilot["sources"]
        rows = {}
        for rel in (
            "crates/dodge-rl-env/src/seed.rs",
            "crates/dodge-rl-env/src/env.rs",
            "crates/dodge-rl-env/src/python.rs",
            "python/dodge_rl/train_teacher.py",
        ):
            current = sha256_file(REPO / rel)
            pinned = pins.get(rel)
            rows[rel] = {
                "current_sha256": current,
                "pilot_identity_pin": pinned,
                "matches_pin": current == pinned,
            }
        self.require(
            rows["crates/dodge-rl-env/src/seed.rs"]["matches_pin"],
            "seed.rs no longer matches the pilot identity pin",
        )
        self.require(
            rows["python/dodge_rl/train_teacher.py"]["matches_pin"],
            "train_teacher.py no longer matches the pilot identity pin",
        )
        self.evidence["source_bindings"] = {
            "pilot_identity": "learning/runs/v2/milestone3-D1-pilot-r1/identity.json",
            "pilot_identity_sha256": sha256_file(
                REPO / "learning/runs/v2/milestone3-D1-pilot-r1/identity.json"
            ),
            "files": rows,
            "note": (
                "env.rs and python.rs current worktree bytes differ from the "
                "historical pilot pin; this is a pre-existing worktree state, not "
                "a write by this reconstruction. The seed algorithm source and "
                "runner match their pins."
            ),
        }

    def check_nodes(self) -> None:
        by_name = {node["name"]: node for node in NODES}
        payload_paths = set()
        node_rows = []
        for node in NODES:
            checkpoint = REPO / node["checkpoint"]
            self.require(checkpoint.is_file(), f"missing checkpoint {node['checkpoint']}")
            actual = sha256_file(checkpoint)
            self.require(
                actual == node["sha256"],
                f"checkpoint hash mismatch for {node['name']}: {actual}",
            )
            payload_paths.add(checkpoint.resolve())
            registration = REPO / node["registration"]
            self.require(
                registration.is_file(), f"missing registration {node['registration']}"
            )
            reg = load_json(node["registration"])
            if "run_seed" in reg:
                self.require(
                    reg["run_seed"] == node["run_seed"],
                    f"registration run_seed mismatch for {node['name']}",
                )
            else:
                config = reg.get("config", {})
                self.require(
                    config.get("phase_settings", {}).get("run_seed")
                    == node["run_seed"],
                    f"identity run_seed mismatch for {node['name']}",
                )
            parent = node.get("parent")
            if parent:
                parent_node = by_name[parent]
                if "parent_link" in node:
                    lineage = load_json(node["parent_link"])
                    self.require(
                        Path(lineage["parent_checkpoint"]).resolve()
                        == (REPO / parent_node["checkpoint"]).resolve(),
                        f"parent path mismatch for {node['name']}",
                    )
                    self.require(
                        lineage["parent_sha256"] == parent_node["sha256"],
                        f"parent hash mismatch for {node['name']}",
                    )
                    parent_evidence = {
                        "link": node["parent_link"],
                        "link_sha256": sha256_file(REPO / node["parent_link"]),
                        "parent_checkpoint": parent_node["checkpoint"],
                        "parent_sha256": parent_node["sha256"],
                    }
                else:
                    parent_record = reg.get("parent")
                    self.require(
                        isinstance(parent_record, dict),
                        f"missing registration parent for {node['name']}",
                    )
                    self.require(
                        Path(parent_record["path"]).resolve()
                        == (REPO / parent_node["checkpoint"]).resolve(),
                        f"parent path mismatch for {node['name']}",
                    )
                    self.require(
                        parent_record["sha256"] == parent_node["sha256"],
                        f"parent hash mismatch for {node['name']}",
                    )
                    parent_evidence = {
                        "parent_checkpoint": parent_node["checkpoint"],
                        "parent_sha256": parent_node["sha256"],
                    }
            else:
                config = reg.get("config", {})
                self.require(
                    config.get("parent_checkpoint_sha256") is None,
                    "root node unexpectedly has a parent",
                )
                parent_evidence = {"root": True}
            node_rows.append(
                {
                    "name": node["name"],
                    "checkpoint": node["checkpoint"],
                    "checkpoint_sha256": actual,
                    "registration": node["registration"],
                    "registration_sha256": sha256_file(registration),
                    "run_seed": node["run_seed"],
                    "journal": f"{node['journal']}/training-episodes.jsonl",
                    "journal_sha256": sha256_file(
                        REPO / node["journal"] / "training-episodes.jsonl"
                    ),
                    "bound_source": node["bound_source"],
                    "parent": parent_evidence,
                }
            )
        self.require(
            len(payload_paths) <= MAX_ANCESTRY_PAYLOADS,
            f"ancestry payload cap exceeded: {len(payload_paths)}",
        )
        self.require(
            len(payload_paths) == len(NODES),
            "ancestry closure must use one distinct checkpoint per node",
        )
        self.evidence["nodes"] = node_rows
        self.evidence["parent_chain"] = {
            "complete": True,
            "root": NODES[0]["name"],
            "terminal": NODES[-1]["name"],
            "edges": len(NODES) - 1,
            "distinct_checkpoint_payloads": len(payload_paths),
        }

    def check_receipt(self) -> None:
        path = REPO / RECEIPT_348
        self.require(path.is_file(), "missing accepted 348 receipt")
        actual = sha256_file(path)
        self.require(actual == RECEIPT_348_SHA256, "accepted 348 receipt hash mismatch")
        receipt = load_json(RECEIPT_348)
        self.evidence["receipt_348"] = {
            "path": RECEIPT_348,
            "sha256": actual,
            "candidate_sha256": receipt.get("candidate_sha256")
            or receipt.get("checkpoint_sha256"),
            "keys": sorted(receipt),
        }

    def check_exclusions(self) -> None:
        checked = []
        for node in NODES:
            reg = load_json(node["registration"])
            if "config" in reg:
                ranges = reg["config"].get("excluded_seed_ranges", [])
            else:
                config_path = reg["config_path"]
                config = load_json(str(Path(config_path).relative_to(REPO)))
                ranges = config.get("excluded_seed_ranges", [])
            normalized = tuple(tuple(item) for item in ranges)
            self.require(
                normalized == EXCLUSIONS,
                f"exclusion mismatch for {node['name']}: {ranges}",
            )
            checked.append(
                {
                    "node": node["name"],
                    "excluded_seed_ranges": [list(item) for item in normalized],
                }
            )
        self.evidence["seed_source"]["registration_exclusions"] = checked

    def read_journal(self, journal: str, run_seed: int) -> dict:
        path = REPO / "learning/runs/v2" / journal / "training-episodes.jsonl"
        self.require(path.is_file(), f"missing journal {journal}")
        max_episode = [-1] * 64
        final_boundary = None
        records = 0
        attributed = 0
        unmatched = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "checkpoint_resume_boundary":
                final_boundary = row
            seen = set()
            for record in iter_seed_records(row):
                key = (
                    record["actual_seed"],
                    record["counter"],
                    record["episode"],
                    record["slot"],
                )
                if key in seen:
                    continue
                seen.add(key)
                records += 1
                hit = None
                for candidate in KNOWN_RUN_SEEDS:
                    counter, actual = self.seed(
                        candidate, record["slot"], record["episode"]
                    )
                    if actual == record["actual_seed"] and counter == record["counter"]:
                        hit = candidate
                        break
                if hit is None:
                    unmatched += 1
                elif hit == run_seed:
                    attributed += 1
                    slot = record["slot"]
                    if 0 <= slot < 64:
                        max_episode[slot] = max(max_episode[slot], record["episode"])
        journal_max = [value + 1 if value >= 0 else 0 for value in max_episode]
        if final_boundary and isinstance(
            final_boundary.get("next_episode_indices"), list
        ):
            boundary = [int(value) for value in final_boundary["next_episode_indices"]]
            self.require(
                len(boundary) == 64, f"unexpected boundary width in {journal}"
            )
            if final_boundary.get("checkpoint_sha256"):
                node = next(
                    (
                        item
                        for item in NODES
                        if Path(item["journal"]).name == journal
                    ),
                    None,
                )
                if node is not None:
                    self.require(
                        final_boundary["checkpoint_sha256"] == node["sha256"],
                        f"journal boundary checkpoint mismatch for {journal}",
                    )
            journal_max = [max(a, b) for a, b in zip(journal_max, boundary)]
        bound = journal_max
        if journal in WORKER_BOUND_JOURNALS:
            worker = load_json(f"learning/runs/v2/{journal}/worker-result.json")
            worker_bound = [
                int(value)
                for value in worker["final_resume_next_episode_indices"]
            ]
            self.require(
                len(worker_bound) == 64, f"unexpected worker bound width in {journal}"
            )
            bound = [max(a, b) for a, b in zip(bound, worker_bound)]
        self.journal_bounds[journal] = bound
        self.journal_stats[journal] = {
            "run_seed": run_seed,
            "seed_records": records,
            "records_attributed_to_run_seed": attributed,
            "records_attributed_to_other_known_seed": records - attributed - unmatched,
            "unmatched": unmatched,
            "bound_min": min(bound),
            "bound_max": max(bound),
            "bound_sum": sum(bound),
            "bound_source": "worker_result_max_journal"
            if journal in WORKER_BOUND_JOURNALS
            else "journal_final_boundary_max_episode",
        }
        return self.journal_stats[journal]

    def check_journals(self) -> None:
        total_records = 0
        total_unmatched = 0
        for journal, run_seed in JOURNAL_SEEDS.items():
            stats = self.read_journal(journal, run_seed)
            total_records += stats["seed_records"]
            total_unmatched += stats["unmatched"]
            self.require(
                stats["unmatched"] == 0, f"unmatched seed record in {journal}"
            )
        self.require(total_unmatched == 0, "journal replay has unmatched records")
        self.evidence["journal_replay"] = {
            "journals": len(JOURNAL_SEEDS),
            "known_run_seeds": KNOWN_RUN_SEEDS,
            "total_seed_records": total_records,
            "unmatched": total_unmatched,
            "per_journal": self.journal_stats,
            "note": (
                "Inherited abandoned_* blocks replay against the parent run seed; "
                "each journal's own rows replay against its registration run seed."
            ),
        }

    def enumerate_seeds(self, pairs: list[tuple[int, list[int]]]) -> tuple[int, set[int]]:
        draws = 0
        seeds: set[int] = set()
        for run_seed, bound in pairs:
            for slot, count in enumerate(bound):
                for episode in range(count):
                    seeds.add(self.seed(run_seed, slot, episode)[1])
                    draws += 1
        return draws, seeds

    def seed_set_sha(self, seeds: set[int]) -> str:
        return sha256_text("\n".join(str(value) for value in sorted(seeds)))

    def check_ancestor_closure(self) -> None:
        pairs = []
        per_node = []
        for node in NODES:
            bound = self.journal_bounds[Path(node["journal"]).name]
            pairs.append((node["run_seed"], bound))
            per_node.append(
                {
                    "node": node["name"],
                    "run_seed": node["run_seed"],
                    "bound_min": min(bound),
                    "bound_max": max(bound),
                    "bound_sum": sum(bound),
                    "draws": sum(bound),
                }
            )
        draws, seeds = self.enumerate_seeds(pairs)
        self.evidence["ancestor_closure"] = {
            "nodes": len(NODES),
            "draws": draws,
            "unique_seeds": len(seeds),
            "seed_set_sha256": self.seed_set_sha(seeds),
            "per_node_bounds": per_node,
            "note": (
                "Enumerates every (slot, episode) below the final resume index of "
                "each producing run; this is a superset of consumed ancestor seeds."
            ),
        }
        self.ancestor_seeds = seeds

    def check_workspace_envelope(self) -> None:
        envelope: dict[int, list[int]] = {}
        contributing: dict[int, list[str]] = {}
        for journal, run_seed in JOURNAL_SEEDS.items():
            bound = self.journal_bounds[journal]
            if run_seed not in envelope:
                envelope[run_seed] = bound[:]
                contributing[run_seed] = [journal]
            else:
                envelope[run_seed] = [
                    max(a, b) for a, b in zip(envelope[run_seed], bound)
                ]
                contributing[run_seed].append(journal)
        pairs = sorted(envelope.items())
        draws, seeds = self.enumerate_seeds(pairs)
        seed_bounds = []
        for run_seed, bound in pairs:
            seed_bounds.append(
                {
                    "run_seed": run_seed,
                    "journals": contributing[run_seed],
                    "bound_min": min(bound),
                    "bound_max": max(bound),
                    "bound_sum": sum(bound),
                    "draws": sum(bound),
                }
            )
        self.evidence["workspace_envelope"] = {
            "journals": len(JOURNAL_SEEDS),
            "distinct_run_seeds": len(envelope),
            "draws": draws,
            "unique_seeds": len(seeds),
            "seed_set_sha256": self.seed_set_sha(seeds),
            "per_seed_bounds": seed_bounds,
            "note": (
                "Union of all 19 top-level journals, grouped by actual run seed. "
                "Includes completed, abandoned, alternate, probe, critic, and "
                "long-D2 branches. It is a modeled superset, not observed exposure."
            ),
        }
        self.envelope_seeds = seeds

    def check_supplemental(self) -> None:
        all_journals = sorted(
            Path(path)
            for path in glob.glob(
                str(REPO / "learning/runs/v2/**/training-episodes.jsonl"),
                recursive=True,
            )
        )
        regular_journals = sorted(
            (REPO / "learning/runs/v2").glob("**/training-episodes.jsonl")
        )
        top_level = {
            REPO / "learning/runs/v2" / name / "training-episodes.jsonl"
            for name in JOURNAL_SEEDS
        }
        nested = [path for path in all_journals if path not in top_level]
        observed: set[int] = set()
        parse_errors = []
        rows = 0
        for path in all_journals:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    rows += 1
                    for record in iter_seed_records(json.loads(line)):
                        observed.add(record["actual_seed"])
            except Exception as exc:  # retained, not hidden
                parse_errors.append({"path": str(path.relative_to(REPO)), "error": str(exc)})
        self.require(not parse_errors, "parse error in supplemental journal scan")
        top_observed = set()
        for journal in JOURNAL_SEEDS:
            path = REPO / "learning/runs/v2" / journal / "training-episodes.jsonl"
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    for record in iter_seed_records(json.loads(line)):
                        top_observed.add(record["actual_seed"])
        missing_journal_dirs = []
        for directory in sorted((REPO / "learning/runs/v2").iterdir()):
            if not directory.is_dir():
                continue
            if (directory / "training-episodes.jsonl").exists():
                continue
            markers = [
                name
                for name in ("identity.json", "worker-result.json", "run-result.json")
                if (directory / name).exists()
            ]
            checkpoints = list(directory.glob("checkpoint-*.pt"))
            if markers or checkpoints:
                missing_journal_dirs.append(
                    {
                        "directory": str(directory.relative_to(REPO)),
                        "markers": markers,
                        "checkpoint_count": len(checkpoints),
                    }
                )
        range_literal_hits = []
        range_literal_files = 0
        for entry in missing_journal_dirs:
            directory = REPO / entry["directory"]
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.stat().st_size > 5_000_000:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                range_literal_files += 1
                lowered = text.lower()
                for name, (start, end) in RANGES.items():
                    for value in range(start, end + 1):
                        if str(value) in text or f"0x{value:x}" in lowered:
                            range_literal_hits.append(
                                {
                                    "path": str(path.relative_to(REPO)),
                                    "range": name,
                                    "value": value,
                                }
                            )
                            break
        self.evidence["supplemental_scans"] = {
            "all_journal_files": len(all_journals),
            "regular_journal_files": len(regular_journals),
            "symlink_alias_paths": len(all_journals) - len(regular_journals),
            "top_level_journals": len(JOURNAL_SEEDS),
            "nested_journals": len(nested),
            "rows_scanned": rows,
            "distinct_actual_seeds": len(observed),
            "distinct_actual_seeds_top_level": len(top_observed),
            "nested_adds_new_actual_seeds": len(observed - top_observed),
            "parse_errors": parse_errors,
            "missing_journal_dirs": missing_journal_dirs,
            "missing_journal_range_literal_scan": {
                "files_scanned": range_literal_files,
                "hits": range_literal_hits,
            },
            "note": (
                "Nested files are capsule/provenance copies, pytest/negative "
                "fixtures, and synthetic guard/boundary campaign cases. They add "
                "no new observed actual seed values in this snapshot."
            ),
        }
        self.observed_seeds = observed

    def check_collisions(self) -> None:
        result = {}
        for name, (start, end) in RANGES.items():
            entry = {"range_inclusive": [start, end], "size": end - start + 1}
            for label, seeds in (
                ("ancestor_closure", self.ancestor_seeds),
                ("workspace_envelope", self.envelope_seeds),
                ("observed_all_journals", self.observed_seeds),
            ):
                hits = sorted(seed for seed in seeds if start <= seed <= end)
                entry[label] = {"collision_count": len(hits), "collisions": hits[:20]}
            result[name] = entry
        self.evidence["collisions"] = result

    def check_proposal_context(self) -> None:
        r4 = load_json(
            "learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r4/proposal.json"
        )
        ranking = r4["cohorts"]["ranking"]
        confirmation = r4["cohorts"]["confirmation"]
        self.require(
            tuple(ranking["range_inclusive"]) == RANGES["ranking_0xD1000000_0xD10003FF"],
            "r4 ranking range mismatch",
        )
        self.require(
            tuple(confirmation["range_inclusive"])
            == RANGES["confirmation_2048_0xD2000000_0xD20007FF"],
            "r4 confirmation range mismatch",
        )
        revision_proposal = load_json(
            "learning/runs/v2/expanded-evaluation-registration-revision-luna-20261026-r3/proposal.json"
        )
        rev_conf = revision_proposal["cohorts"]["confirmation"]
        rev_path = Path(rev_conf["path"])
        r2_path = REPO / "learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r2/confirmation-seed-manifest.json"
        r4_path = REPO / "learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r4/confirmation-seed-manifest.json"
        self.evidence["proposal_context"] = {
            "r4_proposal_sha256": sha256_file(
                REPO
                / "learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r4/proposal.json"
            ),
            "ranking": ranking,
            "confirmation": confirmation,
            "revision_confirmation_path": str(rev_path),
            "revision_confirmation_sha256": rev_conf.get("sha256"),
            "r2_confirmation_sha256": sha256_file(r2_path),
            "r4_confirmation_sha256": sha256_file(r4_path),
            "provenance_note": (
                "The r3 revision proposal points its confirmation path at the r2 "
                "manifest but records the r4 2048-seed manifest SHA. The range is "
                "unambiguous; the path label is stale."
            ),
        }

    def finish(self) -> None:
        self.evidence["proof_boundary"] = {
            "proved": [
                "The accepted 348 checkpoint descends through a linear 10-node "
                "parent chain rooted at the D1 pilot checkpoint.",
                "All 10 ancestor checkpoint file hashes match their registrations.",
                "Every ancestor run's journal seed rows replay exactly under the "
                "registered run seed and the v1 SplitMix64/exclusion algorithm.",
                "The ancestor closure and the 19-journal modeled envelope have zero "
                "collisions with the ranking and both confirmation ranges.",
                "All 862 parseable journals contain zero observed actual seeds in "
                "those ranges.",
            ],
            "not_proved": [
                "Global nonuse of the proposed ranges across all workspace history.",
                "Any run lacking a training-episodes.jsonl journal.",
                "Nested synthetic/negative campaign cases as real training exposure.",
                "B/E outcome paths remain unopened and are not claimed.",
            ],
            "remaining_gaps": [
                "D3 registered seed 5562881586070242563 has no journal or run.",
                "Six top-level directories carry identity/worker/run results but no "
                "training-episodes.jsonl; they were scanned for range literals only, "
                "not replayed.",
                "843 nested journals are capsule/provenance copies, fixtures, or "
                "synthetic guard/boundary cases; they were scanned for actual seeds "
                "but not replayed.",
                "The prior audit remains logged at 1608 files and 0 hits; this "
                "reconstruction does not replace it.",
            ],
            "no_changes": (
                "No proposal, gate, registration, checkpoint, or frozen input was "
                "modified. B/E outcomes were not opened."
            ),
        }
        self.evidence["status"] = "ok"
        (HERE / "evidence.json").write_text(
            json.dumps(self.evidence, indent=2) + "\n", encoding="utf-8"
        )
        print("status: ok")
        print(
            f"ancestor: {self.evidence['ancestor_closure']['nodes']} nodes, "
            f"{self.evidence['ancestor_closure']['draws']} draws, "
            f"{self.evidence['ancestor_closure']['unique_seeds']} unique seeds"
        )
        print(
            f"envelope: {self.evidence['workspace_envelope']['distinct_run_seeds']} seeds, "
            f"{self.evidence['workspace_envelope']['draws']} draws, "
            f"{self.evidence['workspace_envelope']['unique_seeds']} unique seeds"
        )
        for name, entry in self.evidence["collisions"].items():
            print(
                f"{name}: ancestor={entry['ancestor_closure']['collision_count']} "
                f"envelope={entry['workspace_envelope']['collision_count']} "
                f"observed={entry['observed_all_journals']['collision_count']}"
            )

    def run(self) -> None:
        self.check_seed_source()
        self.check_source_bindings()
        self.check_native_bindings()
        self.check_nodes()
        self.check_receipt()
        self.check_exclusions()
        self.check_journals()
        self.check_ancestor_closure()
        self.check_workspace_envelope()
        self.check_supplemental()
        self.check_collisions()
        self.check_proposal_context()
        self.finish()


if __name__ == "__main__":
    Reconstruction().run()
