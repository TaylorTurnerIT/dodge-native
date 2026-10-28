"""Shared constants and pure helpers for the three-run seed-priority recovery packet.

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
PARENT_PKG = V2 / "fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1"  # proven thin parent; read-only here
VALIDATION = V2 / "fullgame-priority-remaining-r3-parent-validation-20261027-r1"
FAILURE = V2 / "fullgame-priority-overnight-interruption-audit-sonnet-20261028-r1"
CHECKPOINT = V2 / "D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt"
PARENT_RECEIPT = V2 / "D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"
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

FAILURE_AUDIT_SHA256 = "032e681c1f0d9393c86f64438deed81c2af2f18d980e56244de8458de1ac4414"
FAILURE_RELEASE_SHA256 = "149827465d03621ab31c2aac16cdac1b25fe62e47b3cd6207ee5f97a881e8b84"
PARENT_RECEIPT_SHA256 = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
FAILED_RUN_ID = STUDY + "-replica-2-opening_priority"
FAILED_REGISTRATION_SHA256 = "db2da67332b51c3cb3839bc8cc08afd1bcca105f64023a47cb8d8da2a0006658"

# Retained completed endpoints (audited, lease released). They are evidence, never relaunched.
COMPLETED = ((1, "opening_priority", PARENT_PKG), (2, "uniform", PARENT_PKG))

# The recovery set: the failed arm restarted from the original parent, then replica 3 in order.
# Order is a suggestion only; every launch is separate.
REMAINING = ((2, "opening_priority"), (3, "uniform"), (3, "opening_priority"))
# Registrations of the same run IDs in the proven parent package; their paths and tokens stay spent/unused.
OLD_CANDIDATE_SHA256 = {
    (2, "opening_priority"): FAILED_REGISTRATION_SHA256,
    (3, "uniform"): "39e1aaacfacc6fe614a8053b64bef9aff2f6ebea08db26a79555a75b57ac2397",
    (3, "opening_priority"): "455442b216aad1501a7c702c0d2563dc0d1e40db46face80c1f74bbcbed7ada9",
}
# Consumed user messages; a recovery authorization must be a different, later message.
CONSUMED_USER_MESSAGES = (
    "You're good to go. Continue overnight. Be efficient with your usage so we don't run out of codex. Free models and cheap claude.",
)
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

LEASE_KIND = "fullgame_seed_priority_recovery_attempt"
INDEX_PROPOSAL_STATUS = "proposal_only_unreviewed_not_promoted_no_launch_authority"
INDEX_PROMOTED_STATUS = "reviewed_exact_registrations_parent_promoted"
GATES_PROPOSAL_STATUS = "proposal_only_requires_independent_review_and_fresh_user_authorization"
GATES_APPROVED_STATUS = "approved_exactly_once_per_registered_run"
GATES_SCHEMA = "fullgame_seed_priority_recovery_r3_parent_gates_v1"
AUTH_SCHEMA = "fullgame_seed_priority_recovery_user_authorization_v1"

# Prior-gate pins that are not carried forward: the broken r2 source bindings and
# the authority/dispatch evidence already consumed by the first attempt.
# Authority and proposal artifacts of earlier packages are never carried into recovery gates.
STALE_AUTHORITY = {
    PARENT_PKG / "fresh-user-authorization.json": "consumed five-run authority",
    PARENT_PKG / "registration-index.json": "old promoted five-run index",
    PARENT_PKG / "registration-index-proposal.json": "old five-run index proposal",
    PARENT_PKG / "parent-gates.json": "old approved gates",
    PARENT_PKG / "parent-gates-proposal.json": "old gates proposal",
    PARENT_PKG / "package-manifest.json": "old package manifest",
    VALIDATION / "remaining-campaign-proposal.json": "old five-run proposal",
    VALIDATION / "authorization-ready.json": "old activation record",
    PRIOR / "fresh-user-authorization.json": "consumed first-run authority",
    PRIOR / "registration-index.json": "first-run index",
    PRIOR / "start_one.py": "first-run launcher",
}
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
