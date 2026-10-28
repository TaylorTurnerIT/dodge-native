"""Build the prospective packet for the five remaining seed-priority r3 runs.

Reads accepted immutable inputs and writes only inside this package, exclusively.
No launch marker, lease, claim, worker output, parent gates or user authorization
is created. Candidates become registrations only through the parent launcher.
"""
from __future__ import annotations
import hashlib
import json
import os
import secrets
import sys

sys.dont_write_bytecode = True
import remaining_plan as p

REGISTRY = p.PROGRAMME / "seed-priority-parent-registry.json"
CORE_PINS = {  # immutable evidence added for the remaining runs
    "first-run registration": p.FIRST_HOME / "registration-final.json",
    "first-run parent terminal audit": p.FIRST_HOME / "parent-terminal-audit.json",
    "first-run lease release": p.FIRST_HOME / "lease-release.json",
}


def write_new(path, value):
    data = p.dump(value) if not isinstance(value, bytes) else value
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return p.sha(path)


def verify_inputs():
    expected = {p.R3 / "source-manifest.json": p.SOURCE_MANIFEST_SHA256,
                p.R3 / "runtime-manifest.json": p.RUNTIME_MANIFEST_SHA256,
                p.SOURCE_ACCEPTANCE: p.SOURCE_ACCEPTANCE_SHA256,
                p.DRAFT_DIR / "draft-index.json": p.DRAFT_INDEX_SHA256,
                p.FIRST_HOME / "registration-final.json": p.FIRST_REGISTRATION_SHA256,
                p.FIRST_HOME / "parent-terminal-audit.json": p.FIRST_AUDIT_SHA256,
                p.FIRST_HOME / "lease-release.json": p.FIRST_LEASE_RELEASE_SHA256}
    for key, digest in p.DRAFT_SHA256.items():
        expected[p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json"] = digest
    for path, digest in expected.items():
        if p.sha(path) != digest:
            raise ValueError("immutable input drift: " + str(path))


def recompute_streams(reg, pool):
    """Independent regeneration of the 64 per-slot stream and component digests."""
    sys.path.insert(0, str(p.R3))
    import seed_priority as sp
    seeds, components = [], []
    for slot, start in enumerate(reg["initial_episode_indices"]):
        entries = sp.sequence_entries(pool, study_id=reg["study_id"], replica=reg["replica"],
            env_master_seed=reg["vector"]["seeds"]["env_master_seed"], arm=reg["arm"],
            slot=slot, count=start + sp.EPISODES_PER_SLOT)
        seeds.append(sp.stream_digest([seed for seed, _ in entries]))
        components.append(sp.stream_digest([component for _, component in entries]))
    return seeds, components


def prior_pins():
    gates = p.read(p.PRIOR / "parent-gates.json")
    excluded = {str(p.V2 / rel) for rel in p.EXCLUDED_PRIOR_PINS}
    return gates, {path: digest for path, digest in gates["pins"].items() if path not in excluded}


def main():
    verify_inputs()
    sys.path.insert(0, str(p.R3))
    import seed_priority as sp
    first = p.to_candidate(p.read(p.DRAFT_DIR / "replica-1-uniform.json"), p.FIRST_HOME,
                           p.FIRST_OWNER_TOKEN, "fullgame_seed_priority_fresh_attempt")
    assert hashlib.sha256(p.dump(first)).hexdigest() == p.FIRST_REGISTRATION_SHA256, "finalization differs from first run"
    registry = p.read(REGISTRY)
    pool = sp.validate_pool(p.read(registry["training_pool_path"]))
    candidates, rows, pin_rows = {}, [], {}
    for replica, arm in p.REMAINING:
        draft = p.read(p.DRAFT_DIR / f"replica-{replica}-{arm}.json")
        assert draft["status"] == "inert_template_NO_LAUNCH" and draft["launch_authority"] is False
        assert draft["source_manifest_sha256"] == p.SOURCE_MANIFEST_SHA256
        assert draft["runtime_manifest_sha256"] == p.RUNTIME_MANIFEST_SHA256
        seeds, components = recompute_streams(draft, pool)
        assert seeds == draft["slot_stream_sha256"] and components == draft["slot_component_sha256"]
        home = p.run_home(replica, arm)
        home.mkdir()
        (home / "empty-pycache").mkdir()
        reg = p.to_candidate(draft, home, secrets.token_hex(16), p.LEASE_KIND)
        candidate = home / "registration-final-candidate.json"
        digest = write_new(candidate, reg)
        pin_rows[str(candidate)] = digest
        rows.append(dict(run_id=reg["run_id"], replica=replica, arm=arm,
            registration=str(home / "registration-final.json"), registration_candidate=str(candidate),
            registration_sha256=digest, source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
            runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256))
    index = dict(schema="fullgame_seed_priority_remaining_index_v1", status=p.INDEX_PROPOSAL_STATUS,
        launch_authority=False, study_id=p.STUDY, runs=rows, source=str(p.R3),
        source_manifest_sha256=p.SOURCE_MANIFEST_SHA256, runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256,
        first_run_not_included=p.FIRST_RUN_ID,
        note="Prospective only. Promotion to registration-index.json is a separate parent step after review and user authorization.")
    index_sha = write_new(p.HERE / "registration-index-proposal.json", index)

    prior, pins = prior_pins()
    for label, path in CORE_PINS.items():
        pins[str(path)] = p.sha(path)
    for replica in (1, 2, 3):
        for name in (f"outputs/replica-{replica}.json", f"reference-approval-replica-{replica}.json"):
            pins[str(p.REF_ROOT / name)] = p.sha(p.REF_ROOT / name)
    pins[str(p.DRAFT_DIR / "draft-index.json")] = p.DRAFT_INDEX_SHA256
    for key, digest in p.DRAFT_SHA256.items():
        pins[str(p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json")] = digest
    pins.update(pin_rows)
    for path, digest in pins.items():
        assert p.sha(path) == digest, path
    # The live ledger/state is mutable. Only the byte-identical immutable snapshot may be pinned.
    assert not any(path.endswith("v2-orchestration/state.json") for path in pins)
    gates = dict(schema=p.GATES_SCHEMA, status=p.GATES_PROPOSAL_STATUS, launch_authority=False,
        authorization="NOT AUTHORIZED. The first Go was consumed by the single uniform replica-1 attempt. "
                      "A fresh user message must name the exact remaining runs and registration SHAs.",
        attempt_policy=prior["attempt_policy"],
        dependency_inventory_path=prior["dependency_inventory_path"],
        dependency_inventory_sha256=prior["dependency_inventory_sha256"],
        dependency_pins_checked=prior["dependency_pins_checked"],
        registration_index_proposal_sha256=index_sha,
        runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256, source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
        runtime_evidence_scope=prior["runtime_evidence_scope"],
        pins=pins, excluded_prior_pins=p.EXCLUDED_PRIOR_PINS,
        consumed_authority_evidence={
            str(p.PRIOR / "fresh-user-authorization.json"): p.sha(p.PRIOR / "fresh-user-authorization.json")},
        required_after_review=["parent-written authorization document (AUTH schema) in this package",
            "gates promoted to parent-gates.json with authorization_path, authorization_sha256 and proposal_sha256",
            "index promoted to registration-index.json with status " + p.INDEX_PROMOTED_STATUS],
        mutable_ledger_policy="state.json is never hash-pinned as immutable history; only seed-history-ledger-snapshot.json is.")
    gates_sha = write_new(p.HERE / "parent-gates-proposal.json", gates)
    receipt = dict(schema="fullgame_seed_priority_remaining_build_receipt_v1", launch_authority=False,
        candidates=pin_rows, registration_index_proposal_sha256=index_sha,
        parent_gates_proposal_sha256=gates_sha, stream_recomputation="passed_all_64_slots_5_runs",
        first_run_transformation_reproduced_sha256=p.FIRST_REGISTRATION_SHA256,
        pins_total=len(pins))
    write_new(p.HERE / "build-receipt.json", receipt)
    print(json.dumps(dict(runs=len(rows), pins=len(pins), index=index_sha, gates=gates_sha), sort_keys=True))


if __name__ == "__main__":
    main()
