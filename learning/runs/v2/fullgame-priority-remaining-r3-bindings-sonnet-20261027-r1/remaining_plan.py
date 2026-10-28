"""Shared constants and pure helpers for the remaining seed-priority r3 bindings.

Stdlib only. Importing this module reads nothing and writes nothing.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
V2 = ROOT / "learning/runs/v2"
R3 = V2 / "fullgame-seed-priority-experiment-luna-20261027-r3"
PRIOR = V2 / "fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1"
REF_ROOT = V2 / "fullgame-priority-rng-reference-parent-20261027-r1"
PROGRAMME = V2 / "rl-next-experiments-parent-20261027-r1"
STUDY = "fullgame-seed-priority-luna-20261027-r1"

SOURCE_MANIFEST_SHA256 = "a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2"
RUNTIME_MANIFEST_SHA256 = "e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986"
CHECKPOINT_SHA256 = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
SOURCE_ACCEPTANCE = PRIOR / "source-acceptance.json"
SOURCE_ACCEPTANCE_SHA256 = "9b2a4bde33ac81453f0aa15079e7dd59a8c746da3de2ad56b352e8a83f8dfb03"

FIRST_RUN_ID = STUDY + "-replica-1-uniform"
FIRST_HOME = PRIOR / FIRST_RUN_ID
FIRST_REGISTRATION_SHA256 = "015464219f2da1f6f69867c94558d5b406f82ee70b7dffa1a38d3c9ab9c820fa"
FIRST_AUDIT_SHA256 = "9d3902d8469d5910d594aeaecd659efd9bd1e970ffd1b9832fb1f00dcd9ef6ac"
FIRST_LEASE_RELEASE_SHA256 = "6a0ba593bd1759bed03c78c18fd8a1b1991b30851bb456240cd944f4904f81a0"
FIRST_OWNER_TOKEN = "13c32efc846e49d19a817a2194566537"

# Order is a suggestion only; the parent chooses and every launch is separate.
REMAINING = ((1, "opening_priority"), (2, "uniform"), (2, "opening_priority"),
             (3, "uniform"), (3, "opening_priority"))
DRAFT_DIR = R3 / "registrations-gated-r3-20261027"
DRAFT_SHA256 = {
    (1, "uniform"): "9816698ea6d6cf3718695c3d5cf0dce11ba69ecde0bff6c57ad346c7217d4e57",
    (1, "opening_priority"): "305a578fcce2f2c73c29913c044500b92773976726e7375ab6c78d9c9aa4506b",
    (2, "uniform"): "145679b212cf5dbceca0738856012729ff5d304f78d10e09513cddb10a3c3e5d",
    (2, "opening_priority"): "0f6d4a298ada69565c273020fb3ecd96821a7d25f213eaccb79125cabd7af898",
    (3, "uniform"): "38531e5e310a8efeb7195768197796353b72d588ba70ab970d469849c61c0467",
    (3, "opening_priority"): "c197844fefc7046350a982500ff0ed135268913a4c8b042be9acfed027d84bc3",
}
DRAFT_INDEX_SHA256 = "bfb35cca05f7047084a34c3b01f0e5aeb5f36e5788ca114d48fc4e7e47cde803"

LEASE_KIND = "fullgame_seed_priority_remaining_attempt"
INDEX_PROPOSAL_STATUS = "proposal_only_unreviewed_not_promoted_no_launch_authority"
INDEX_PROMOTED_STATUS = "reviewed_exact_registrations_parent_promoted"
GATES_PROPOSAL_STATUS = "proposal_only_requires_independent_review_and_fresh_user_authorization"
GATES_APPROVED_STATUS = "approved_exactly_once_per_registered_run"
GATES_SCHEMA = "fullgame_seed_priority_remaining_r3_parent_gates_v1"
AUTH_SCHEMA = "fullgame_seed_priority_remaining_user_authorization_v1"

# Prior-gate pins that are not carried forward: the broken r2 source bindings and
# the authority/dispatch evidence already consumed by the first attempt.
EXCLUDED_PRIOR_PINS = {
    "fullgame-seed-priority-experiment-luna-20261027-r2/runtime-manifest.json": "broken r2 binding; r3 manifests pinned instead",
    "fullgame-seed-priority-experiment-luna-20261027-r2/source-manifest.json": "broken r2 binding; r3 manifests pinned instead",
    "fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1/fresh-user-authorization.json": "consumed single-run authority",
    "fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1/start_one.py": "first-run launcher; new launcher is pinned by review",
    "fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1/registration-index.json": "first-run index",
}


def run_id(replica, arm):
    return f"{STUDY}-replica-{replica}-{arm}"


def run_home(replica, arm):
    return HERE / run_id(replica, arm)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def dump(value):
    """Same serialization as the parent's atomic JSON writer."""
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def to_candidate(draft, home, owner_token, lease_kind):
    """Turn an inert r3 draft into a parent-registration candidate for `home`.

    Mirrors the first-attempt finalization: draft + run-owned paths + exact lease.
    """
    home = Path(home)
    reg = json.loads(json.dumps(draft))
    reg["status"] = "parent_registered"
    reg["launch_authority"] = True
    reg["pending_parent_fields"] = []
    reg["priority"] = {key: reg["priority"][key]
                       for key in ("uniform_floor", "hard_component", "sampling_probability")}
    reg["output"] = str(home / "worker-output")
    reg["attempt_claim_path"] = str(home / "attempt.claimed")
    reg["launch_marker_path"] = str(home / "launch.claimed")
    reg["import_policy"] = {"dont_write_bytecode": True, "pycache_prefix": str(home / "empty-pycache")}
    reg["expected_lease"] = {"MPS_driver_bytes": reg["limits"]["mps_bytes"],
        "RSS_bytes": reg["limits"]["rss_bytes"], "arm": reg["arm"], "kind": lease_kind,
        "owner_token": owner_token, "replica": reg["replica"], "run_id": reg["run_id"],
        "study_id": reg["study_id"]}
    return reg
