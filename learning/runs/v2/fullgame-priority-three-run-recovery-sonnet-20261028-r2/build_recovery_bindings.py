"""Build the prospective packet for the three-run seed-priority recovery.

Reads accepted immutable inputs and writes only inside this package, exclusively.
No launch marker, lease, claim, worker output, parent gates or user authorization
is created. Candidates become registrations only through the parent launcher.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import secrets
import sys

sys.dont_write_bytecode = True
import remaining_plan as p

REGISTRY = p.PROGRAMME / "seed-priority-parent-registry.json"
D4_PLAN = p.V2 / "fullgame-priority-D4-evaluator-sonnet-20261028-r2/policy-plan.json"
TEMPLATE = p.VALIDATION / "reviewed-gates-template.json"
PARENT_CODE = ("remaining_plan.py", "start_remaining_one.py", "watch_progress.py", "build_remaining_bindings.py")
OWN_CODE = ("remaining_plan.py", "start_remaining_one.py", "watch_progress.py", "power_guard.py",
            "probe_power_guard.py", "build_recovery_bindings.py")
# Candidate fields that may differ from the same run's registration in the proven parent package.
RUN_PRIVATE = {"output", "attempt_claim_path", "launch_marker_path", "import_policy", "expected_lease"}


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
                p.FIRST_HOME / "lease-release.json": p.FIRST_LEASE_RELEASE_SHA256,
                p.FAILURE / "audit.json": p.FAILURE_AUDIT_SHA256,
                p.FAILURE / "lease-release.json": p.FAILURE_RELEASE_SHA256,
                p.CHECKPOINT: p.CHECKPOINT_SHA256,
                p.PARENT_RECEIPT: p.PARENT_RECEIPT_SHA256}
    for key, digest in p.DRAFT_SHA256.items():
        expected[p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json"] = digest
    for key, digest in p.OLD_CANDIDATE_SHA256.items():
        expected[p.PARENT_PKG / p.run_id(*key) / "registration-final-candidate.json"] = digest
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


def base_pins():
    """Reviewed parent pins minus every stale authority/proposal/index and the old package's run files."""
    template = p.read(TEMPLATE)
    stale = {str(path) for path in p.STALE_AUTHORITY}
    return template, {path: digest for path, digest in template["pins"].items()
                      if path not in stale and not path.startswith(str(p.PARENT_PKG))}


def completed_pins():
    pins = {}
    for replica, arm, package in p.COMPLETED:
        home = package / p.run_id(replica, arm)
        for name in ("registration-final.json", "execution-exit.json", "parent-terminal-audit.json", "lease-release.json"):
            pins[str(home / name)] = p.sha(home / name)
    return pins


def producer_home_remap(rows):
    """Original D4 r2 policy paths for the three re-homed endpoints and their proposed recovery paths."""
    plan = p.read(D4_PLAN)
    by_run = {policy.get("run_id"): policy for policy in plan["policies"]}
    remap = {}
    for row in rows:
        original = by_run[row["run_id"]]
        old_home, new_home = str(p.PARENT_PKG / row["run_id"]), str(p.HERE / row["run_id"])
        proposed = {key: (value.replace(old_home, new_home) if isinstance(value, str) else value)
                    for key, value in original.items()}
        remap[row["run_id"]] = dict(original=original, proposed=proposed,
            changed_keys=sorted(key for key in original if original[key] != proposed[key]),
            recovery_registration_candidate_sha256=row["registration_sha256"],
            expected_registration_final_sha256=row["registration_sha256"])
    return plan, dict(schema="fullgame_priority_producer_home_remap_v1", launch_authority=False,
        study_id=p.STUDY, d4_policy_plan=str(D4_PLAN), d4_policy_plan_sha256=p.sha(D4_PLAN),
        status="proposal_only_not_applied_d4_plan_unmodified",
        note="Only the three recovery endpoints are remapped; all six terminal60 endpoints stay fixed before D4 opens. "
             "The root writes a reviewed evaluator successor or registration-binding adaptation; no subset evaluation, "
             "no replacement of fixed policies by partial ones.",
        endpoints=remap)


def main():
    verify_inputs()
    sys.path.insert(0, str(p.R3))
    import seed_priority as sp
    first = p.to_candidate(p.read(p.DRAFT_DIR / "replica-1-uniform.json"), p.FIRST_HOME,
                           p.FIRST_OWNER_TOKEN, "fullgame_seed_priority_fresh_attempt")
    assert hashlib.sha256(p.dump(first)).hexdigest() == p.FIRST_REGISTRATION_SHA256, "finalization differs from first run"
    built_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    registry = p.read(REGISTRY)
    pool = sp.validate_pool(p.read(registry["training_pool_path"]))
    rows, pin_rows = [], {}
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
        token = secrets.token_hex(16)
        reg = p.to_candidate(draft, home, token, p.LEASE_KIND)
        old = p.read(p.PARENT_PKG / p.run_id(replica, arm) / "registration-final-candidate.json")
        differing = {key for key in set(reg) | set(old) if reg.get(key) != old.get(key)}
        assert differing == RUN_PRIVATE, differing  # same vector, pool, references, budgets; only private paths/lease
        assert token != old["expected_lease"]["owner_token"]
        candidate = home / "registration-final-candidate.json"
        digest = write_new(candidate, reg)
        pin_rows[str(candidate)] = digest
        rows.append(dict(run_id=reg["run_id"], replica=replica, arm=arm,
            registration=str(home / "registration-final.json"), registration_candidate=str(candidate),
            registration_sha256=digest, source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
            runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256,
            superseded_registration_sha256=p.OLD_CANDIDATE_SHA256[(replica, arm)]))
    index = dict(schema="fullgame_seed_priority_recovery_index_v1", status=p.INDEX_PROPOSAL_STATUS,
        launch_authority=False, user_approval="NOT_GIVEN", study_id=p.STUDY, runs=rows, source=str(p.R3),
        source_manifest_sha256=p.SOURCE_MANIFEST_SHA256, runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256,
        retained_completed=[p.run_id(r, a) for r, a, _ in p.COMPLETED] + [p.FIRST_RUN_ID],
        failed_not_continued=p.FAILED_RUN_ID,
        note="Prospective only. Promotion to registration-index.json is a separate parent step after review and fresh user approval.")
    index_sha = write_new(p.HERE / "registration-index-proposal.json", index)

    plan, remap = producer_home_remap(rows)
    remap_sha = write_new(p.HERE / "producer-home-remap.json", remap)

    template, pins = base_pins()
    pins.update(completed_pins())
    for name in ("audit.json", "lease-release.json", "incident-summary.json", "interruption_audit.py"):
        pins[str(p.FAILURE / name)] = p.sha(p.FAILURE / name)
    pins[str(p.CHECKPOINT)] = p.CHECKPOINT_SHA256
    pins[str(p.CHECKPOINT) + ".json"] = p.sha(str(p.CHECKPOINT) + ".json")
    pins[str(p.PARENT_RECEIPT)] = p.PARENT_RECEIPT_SHA256
    pins[str(D4_PLAN)] = p.sha(D4_PLAN)
    for name in PARENT_CODE:
        pins[str(p.PARENT_PKG / name)] = p.sha(p.PARENT_PKG / name)
    for name in OWN_CODE:
        pins[str(p.HERE / name)] = p.sha(p.HERE / name)
    pins[str(p.HERE / "producer-home-remap.json")] = remap_sha
    pins[str(p.HERE / "registration-index-proposal.json")] = index_sha
    pins.update(pin_rows)
    for path, digest in pins.items():
        assert p.sha(path) == digest, path
    assert not any(path.endswith("v2-orchestration/state.json") for path in pins)  # mutable ledger never pinned
    assert not any(path in {str(x) for x in p.STALE_AUTHORITY} for path in pins)
    gates = dict(schema=p.GATES_SCHEMA, status=p.GATES_PROPOSAL_STATUS, launch_authority=False,
        packet_built_at_utc=built_at,
        authorization="NOT AUTHORIZED. Prior Go consumed by the aborted five-run sequence. "
                      "A fresh explicit user message approving this concrete three-run plan is required; no typed hashes needed.",
        attempt_policy=template["attempt_policy"],
        dependency_inventory_path=template["dependency_inventory_path"],
        dependency_inventory_sha256=template["dependency_inventory_sha256"],
        dependency_pins_checked=template["dependency_pins_checked"],
        registration_index_proposal_sha256=index_sha,
        runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256, source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
        runtime_evidence_scope="Same r3 worker source and runtime. Completed audited controls: replica-1 uniform, replica-1 opening_priority, "
                               "replica-2 uniform. Replica-2 opening_priority attempt was interrupted at 5 durable updates (audited).",
        failure_audit_sha256=p.FAILURE_AUDIT_SHA256, failure_lease_release_sha256=p.FAILURE_RELEASE_SHA256,
        checkpoint_sha256=p.CHECKPOINT_SHA256,
        accounting="The 5 durable updates of the interrupted attempt are discarded infrastructure waste: not a continuation, "
                   "not endpoint selection. replica-2 opening_priority restarts from original accepted parent324 + Adam + the same "
                   "six-key RNG vector. Completed replica-2 uniform is retained.",
        pins=pins, excluded_stale_authority={str(path): why for path, why in p.STALE_AUTHORITY.items()},
        excluded_prior_pins=p.EXCLUDED_PRIOR_PINS,
        consumed_authority_evidence={
            str(p.PRIOR / "fresh-user-authorization.json"): p.sha(p.PRIOR / "fresh-user-authorization.json"),
            str(p.PARENT_PKG / "fresh-user-authorization.json"): p.sha(p.PARENT_PKG / "fresh-user-authorization.json")},
        required_after_review=[
            "independent_review {path, sha256, package_manifest_sha256}, with the review file and package-manifest.json pinned",
            "parent-written authorization (AUTH schema): verbatim fresh user message after packet_built_at_utc, three run/SHA pairs, "
            "index_proposal_sha256, failure_audit_sha256, retries 0",
            "gates promoted to parent-gates.json with status " + p.GATES_APPROVED_STATUS + ", authorization_path/sha256, proposal_sha256, "
            "registration_index_sha256, plus the pins above",
            "index promoted to registration-index.json with status " + p.INDEX_PROMOTED_STATUS],
        mutable_ledger_policy="state.json is never hash-pinned as immutable history; only seed-history-ledger-snapshot.json is.")
    gates_sha = write_new(p.HERE / "parent-gates-proposal.json", gates)
    receipt = dict(schema="fullgame_seed_priority_recovery_build_receipt_v1", launch_authority=False,
        packet_built_at_utc=built_at, candidates=pin_rows, registration_index_proposal_sha256=index_sha,
        parent_gates_proposal_sha256=gates_sha, producer_home_remap_sha256=remap_sha,
        stream_recomputation="passed_all_64_slots_3_runs",
        candidate_vs_parent_package_diff="only output, attempt_claim_path, launch_marker_path, import_policy, expected_lease",
        pins_total=len(pins), d4_plan_sha256_unmodified=p.sha(D4_PLAN))
    write_new(p.HERE / "build-receipt.json", receipt)
    print(json.dumps(dict(runs=len(rows), pins=len(pins), index=index_sha, gates=gates_sha,
                          candidates={r["run_id"]: r["registration_sha256"] for r in rows}), sort_keys=True))


if __name__ == "__main__":
    main()
