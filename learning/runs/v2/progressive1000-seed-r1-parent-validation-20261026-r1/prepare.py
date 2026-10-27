"""Owned-output preparation. Standard-library reads, hashes and arithmetic only.

Run from any directory with python3 -B and PYTHONPYCACHEPREFIX pointing to the
owned empty-pycache. No predecessor Python source is imported or executed.
"""
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from seed_controls import (BOUNDS, DOMAIN, HISTORICAL_RANGES, NAMED_RANGES,
                           STUDY_ID, canonical, derive, digest, normalize,
                           require_training_union, training_seed)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUNS = REPO / "learning/runs/v2"
INPUTS = {}
DESIGN = "learning/runs/v2/progressive1000-curriculum-replica-parent-20261026-r3/experiment.json"
PARENT = "learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"
LINEAGE = "learning/runs/v2/expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/evidence.json"
PINNED = {
    DESIGN: "c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0",
    PARENT: "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08",
    LINEAGE: "5c0ab35cf9e6fd4a353093f29a9875ab2ec1b91092358afecc7003ba79176670",
    "crates/dodge-rl-env/src/seed.rs": "239cb9d88a61fff7d63c3c13c80e4552caafe814729160f8fb2948d3c1498832",
    "learning/runs/v2/PPO-RNG-seed-vectors-parent-20261026-r2/stdlibderive.py": "5cb2bb8c0031c3a39703348dcefbb8edb38d0adbcc5afbc77a3b0923e3f869e0",
    "learning/runs/v2/expanded-confirmation-parent-20261026-r1/parent-acceptance.json": "3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd",
}


def forbidden(path):
    # Conservative path-only boundary. Never open qualification outcomes or
    # their seed/run metadata. Reserved range constants are supplied above.
    return bool(re.search(r"(?i)((?<![a-z0-9])(?:B1000|E1000)(?![a-z0-9])|qualification|holdout|(?:^|[/_-])(?:B|E)(?:-campaign|-execution|-evaluation|/outputs))", str(path)))


def read(path, purpose, hash_only=False):
    path = Path(path)
    if not path.is_absolute():
        path = REPO / path
    if forbidden(path.relative_to(REPO)) or forbidden(path.resolve().relative_to(REPO)):
        raise ValueError(f"forbidden qualification input: {path}")
    if path.suffix in (".pt", ".so", ".dylib", ".npz", ".npy"):
        raise ValueError("binary/model input not permitted by this helper")
    data = path.read_bytes()
    key = str(path.relative_to(REPO))
    sha = hashlib.sha256(data).hexdigest()
    if key in PINNED and sha != PINNED[key]:
        raise ValueError(f"pinned input mismatch: {key}: {sha}")
    if key in INPUTS and INPUTS[key]["sha256"] != sha:
        raise ValueError(f"input changed during preparation: {key}")
    row = INPUTS.setdefault(key, {"path": key, "sha256": sha, "bytes": len(data), "purposes": []})
    if purpose not in row["purposes"]:
        row["purposes"].append(purpose)
    return None if hash_only else data


def load(path, purpose):
    return json.loads(read(path, purpose))


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def walk(value, pointer=""):
    if isinstance(value, dict):
        yield pointer, value
        for key, child in value.items():
            yield from walk(child, pointer + "/" + str(key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, pointer + "/" + str(i))


def seed_records(value):
    for pointer, row in walk(value):
        if all(type(row.get(k)) is int for k in ("actual_seed", "counter", "episode", "slot")):
            yield pointer, row


def real_records(value):
    """Explicit constructed seed metadata, or outcome-bearing raw episode rows.

    Bare seed numbers/configs/proposed vectors never establish consumption.
    Extraction from real result aggregates may repeat raw logs; counts are
    records, not distinct executed episodes. Seed values are deduplicated.
    """
    for pointer, row in walk(value):
        if type(row.get("actual_seed")) is int:
            if all(type(row.get(k)) is int for k in ("slot", "episode", "counter")):
                yield pointer, row["actual_seed"], "evaluation" if row.get("evaluation") else "training"
            else:
                yield pointer, row["actual_seed"], "unresolved_actual_seed_metadata"
        elif type(row.get("seed")) is int and any(k in row for k in (
                "alive_frames", "gameplay_frames", "raw_frames", "terminated", "full_state_hash")):
            yield pointer + "/seed", row["seed"], "evaluation_or_probe"


SYNTHETIC = re.compile(r"(?i)(fixture|synthetic|fake[-_/]|test-tmp|test_tmp|pytest|/test_|/tests?(?:/|-and-receipts/)|reproduction|/positive-controls/|/negative|/case[-_/]|/cases/|replay[-_])")
COPIED = re.compile(r"(?i)(/provenance/|/history/|/source-before/|/originals/|/source/|/runtime/|/capsule/|/attempts/)")
FUTURE = re.compile(r"(?i)(prepare|proposal|registration|seed-vectors|design|reference|collector|integrat|proof|review|validation|repair)")


def classify(rel, journal_runs):
    text = str(rel)
    if forbidden(rel):
        return "qualification_excluded_unopened"
    if SYNTHETIC.search("/" + text):
        return "synthetic_fixture_or_replay"
    if COPIED.search("/" + text):
        return "copied_source_or_provenance"
    if rel.parts[0] in journal_runs:
        return "real_journal_run"
    if rel.parts[0] in {
        "postovernight-action-mode-campaign-r1", "milestone0-campaign-r2",
        "milestone2-validation-campaign-r1", "milestone2-validation-campaign-r2",
        "expanded-ranking-parent-20261026-r1", "expanded-confirmation-parent-20261026-r1",
        "expanded-dev64-benchmark-parent-20261026-r1",
    }:
        return "real_evaluation_probe_or_benchmark"
    if FUTURE.search(rel.parts[0]):
        return "proposal_or_unqualified_control"
    return "unresolved_execution_provenance"


def reconstruct(lineage):
    mapping = {name: row["run_seed"] for name, row in lineage["journal_replay"]["per_journal"].items()}
    masters = sorted(set(mapping.values()))
    cache = {}
    observed = set()
    reconstructed = set()
    bounds = []
    replay_controls = []
    unmatched = []
    for name, master in sorted(mapping.items()):
        journal = RUNS / name / "training-episodes.jsonl"
        data = read(journal, "original training journal and exact tuple replay")
        per_slot = [0] * 64
        samples = set()
        count = 0
        inherited = 0
        per_kind = collections.Counter()
        for lineno, raw in enumerate(data.splitlines(), 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            kind = row.get("kind", "unspecified")
            per_kind[kind] += 1
            indices = row.get("next_episode_indices")
            if isinstance(indices, list) and len(indices) == 64:
                per_slot = [max(a, b) for a, b in zip(per_slot, indices)]
            seen = set()
            for pointer, record in seed_records(row):
                key = tuple(record[k] for k in ("slot", "episode", "counter", "actual_seed"))
                if key in seen:
                    continue
                seen.add(key)
                count += 1
                observed.add(record["actual_seed"])
                slot, episode, counter, actual = key
                hit = None
                for test_master in [master] + [m for m in masters if m != master]:
                    ck = (test_master, slot, episode)
                    if ck not in cache:
                        result = training_seed(test_master, slot, episode)
                        cache[ck] = (result["counter"], result["actual_seed"])
                    if cache[ck] == (counter, actual):
                        hit = test_master
                        break
                if hit is None:
                    unmatched.append({"path": str(journal.relative_to(REPO)), "line": lineno, "pointer": pointer, "metadata": record})
                elif hit == master:
                    per_slot[slot] = max(per_slot[slot], episode + 1)
                    samples.add((slot, episode, counter, actual))
                else:
                    inherited += 1
        worker = RUNS / name / "worker-result.json"
        if worker.exists():
            result = load(worker, "original terminal counters for discarded and retained work")
            indices = result.get("final_resume_next_episode_indices")
            if isinstance(indices, list) and len(indices) == 64:
                per_slot = [max(a, b) for a, b in zip(per_slot, indices)]
        before = len(reconstructed)
        for slot, bound in enumerate(per_slot):
            # Inclusive extra endpoint protects a possibly constructed current
            # episode; zero-to-bound is a conservative envelope, not evidence
            # that unused inherited indices executed under a new master.
            for episode in range(bound + 1):
                reconstructed.add(training_seed(master, slot, episode)["actual_seed"])
        bounds.append({"run": name, "run_master_seed": master,
                       "inclusive_per_slot_bounds": per_slot, "draws": sum(x + 1 for x in per_slot),
                       "new_unique_envelope_values": len(reconstructed) - before,
                       "observed_seed_records_deduplicated_within_row": count,
                       "inherited_parent_records": inherited, "row_kinds": dict(per_kind),
                       "scope": "original full journal plus available final worker; includes discarded updates and aborted branches; missing failed resets remain a gap"})
        for slot, episode, counter, actual in sorted(samples)[:4]:
            replay_controls.append({"run_master_seed": master, "slot": slot, "episode": episode,
                                    "counter": counter, "actual_seed": actual,
                                    "source": str(journal.relative_to(REPO))})
    write("history-reconstruction.json", {"bounds": bounds, "reference_vectors": replay_controls,
          "unmatched": unmatched, "unique_logged_training_seeds": len(observed),
          "unique_conservative_envelope_seeds": len(reconstructed),
          "claim": "Conservative finite 19-journal construction envelope, not actual episode count or global workspace history"})
    return mapping, observed, reconstructed, unmatched


def scan(mapping):
    inventory = []
    selected = []
    # Complete path inventory, no hidden native/source execution. Path-only
    # exclusions are recorded, rather than reading qualification files first.
    for base, dirs, names in os.walk(RUNS, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "empty-pycache", ".git") and (Path(base) / d) != HERE)
        for name in sorted(names):
            path = Path(base) / name
            if path.suffix not in (".json", ".jsonl"):
                continue
            rel = path.relative_to(RUNS)
            category = classify(rel, mapping)
            entry = {"path": str(path.relative_to(REPO)), "category": category,
                     "bytes_stat_only": path.stat().st_size, "opened": False}
            inventory.append(entry)
            if category in ("qualification_excluded_unopened", "synthetic_fixture_or_replay", "copied_source_or_provenance"):
                continue
            # All potentially original JSONL logs; all metadata/outcome JSON in
            # known real contexts; other explicit seed/episode/eval/probe data.
            if path.suffix == ".jsonl" or category.startswith("real_") or re.search(r"(?i)(seed|episode|benchmark|calibration|probe|evaluation)", name):
                selected.append((path, entry))
    observed = set()
    unresolved = set()
    future_values = set()
    collisions = []
    errors = []
    per_category = collections.defaultdict(collections.Counter)
    canonical_hashes = {}
    per_file = []
    for path, entry in selected:
        cat = entry["category"]
        if forbidden(path.resolve().relative_to(REPO)):
            entry["category"] = "qualification_target_excluded_unopened"
            continue
        data = read(path, "seed exposure scan: " + cat)
        entry["opened"] = True
        sha = INPUTS[str(path.relative_to(REPO))]["sha256"]
        if sha in canonical_hashes:
            entry["content_duplicate_of"] = canonical_hashes[sha]
            # Scan the real original even if an unresolved aggregate came first.
            if not cat.startswith("real_"):
                continue
        else:
            canonical_hashes[sha] = entry["path"]
        local = set()
        records = 0
        explicit_values = set()
        if path.suffix == ".jsonl":
            raw_rows = enumerate(data.splitlines(), 1)
        else:
            raw_rows = [(0, data)]
        for lineno, raw in raw_rows:
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                errors.append({"path": entry["path"], "line": lineno, "error": str(exc), "category": cat})
                continue
            for pointer, row in walk(value):
                for key in ("actual_seed", "seed", "environment_seed", "seed_id", "master_seed", "run_seed", "env_master_seed"):
                    if type(row.get(key)) is int:
                        explicit_values.add(row[key])
            seen = set()
            for pointer, seed, kind in real_records(value):
                token = (pointer, seed, kind)
                if token in seen:
                    continue
                seen.add(token)
                records += 1
                local.add(seed)
                per_category[cat][kind + "_records"] += 1
                if cat.startswith("real_") and kind != "unresolved_actual_seed_metadata":
                    observed.add(seed)
                    provenance = "real_observed"
                elif cat == "proposal_or_unqualified_control":
                    future_values.add(seed)
                    provenance = "proposal_or_unqualified_control"
                else:
                    unresolved.add(seed)
                    provenance = "unresolved_provenance"
                if 0xD3000000 <= seed <= 0xD30003FF:
                    collisions.append({"seed": seed, "path": entry["path"], "line": lineno,
                                       "pointer": pointer, "kind": kind, "provenance": provenance})
        per_category[cat]["files_scanned"] += 1
        # Bare metadata may be a construction not represented by raw rows. Keep
        # collision evidence without converting future configs into episodes.
        for seed in sorted(explicit_values):
            if 0xD3000000 <= seed <= 0xD30003FF and seed not in local:
                collisions.append({"seed": seed, "path": entry["path"], "kind": "explicit_seed_metadata_only",
                                   "provenance": "unresolved_or_future_metadata", "line": None})
        per_file.append({"path": entry["path"], "sha256": sha, "category": cat,
                         "seed_records": records, "distinct_episode_seed_values": len(local),
                         "distinct_explicit_seed_metadata_values": len(explicit_values)})
    write("coverage-inventory.json", inventory)
    write("coverage-files.json", per_file)
    return observed, unresolved, future_values, collisions, errors, {k: dict(v) for k, v in per_category.items()}, inventory


def main():
    if not sys.dont_write_bytecode or Path(sys.pycache_prefix or "").resolve() != HERE / "empty-pycache":
        raise ValueError("use -B and the owned empty-pycache prefix")
    if any((HERE / "empty-pycache").iterdir()):
        raise ValueError("owned cache must be empty")
    for path in PINNED:
        read(path, "explicit pin verification", hash_only=True)
    design = load(DESIGN, "accepted curriculum proposal contract")
    parent = load(PARENT, "accepted324 exact counters and slot offsets")
    lineage = load(LINEAGE, "prior lineage source and execution inventory")
    old = load("learning/runs/v2/confirmed324-seed-vectors-parent-20261026-r1/seed-vectors.json", "derivation and parent offsets only; no LR values or references reused")
    if parent["checkpoint_sha256"] != "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc":
        raise ValueError("checkpoint identity mismatch")
    if parent["candidate_phase_update"] != 324 or parent["cumulative_counters"]["updates"] != 372:
        raise ValueError("parent counters mismatch")
    offsets = parent["next_episode_indices"]
    if len(offsets) != 64 or offsets != old["parent"]["next_episode_indices"]:
        raise ValueError("parent slot index mismatch")
    for path in (
        "learning/runs/v2/expanded-seed-lineage-parent-validation-20261026-r5/receipt.json",
        "learning/runs/v2/expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/manifest.json",
        "learning/runs/v2/expanded-evaluation-seed-exposure-audit-luna-20261026-r1/audit.json",
        "learning/runs/v2/expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/reconciliation.json",
        "crates/dodge-rl-env/src/seed_reservation_tests.rs",
        "crates/dodge-rl-env/src/seed_extension_tests.rs",
        "learning/runs/v2/confirmed324-probe-finalization-repair-sol-20261026-r5/probe.py",
    ):
        read(path, "historical scope or proposed control compatibility")
    mapping, logged, envelope, unmatched = reconstruct(lineage)
    print("Original journal replay complete", len(logged), "unique logged seeds; unmatched", len(unmatched), flush=True)
    observed, unresolved, future, hits, errors, categories, inventory = scan(mapping)
    observed |= logged
    union = normalize(list(NAMED_RANGES.values()))
    for arm in ("control", "curriculum"):
        require_training_union(union, arm)
    prior_masters = sorted(set(mapping.values()) | set(old["derivation"]["prior_master_seeds_rejected"]))
    vectors = [derive(i, prior_masters) for i in (1, 2, 3)]
    for field in BOUNDS:
        if len({v["seeds"][field] for v in vectors}) != 3:
            raise ValueError("replica field reuse")
    initial = []
    bounded = []
    history = observed | envelope
    future_seen = {}
    future_collisions = []
    for vector in vectors:
        master = vector["seeds"]["env_master_seed"]
        rows = [training_seed(master, slot, episode, union) for slot, episode in enumerate(offsets)]
        initial.append({"replica": vector["replica"], "vector_sha256": vector["vector_sha256"], "slots": rows,
                        "actual_seeds_u32be_sha256": hashlib.sha256(b"".join(r["actual_seed"].to_bytes(4, "big") for r in rows)).hexdigest()})
        sample = []
        repeats = []
        historical = []
        for slot, start in enumerate(offsets):
            for episode in range(start, start + 512):
                row = training_seed(master, slot, episode, union)
                seed = row["actual_seed"]
                key = {"replica": vector["replica"], "slot": slot, "episode": episode, "counter": row["counter"], "actual_seed": seed}
                if seed in history:
                    historical.append({**key, "in_real_observed": seed in observed,
                                       "in_conservative_envelope": seed in envelope,
                                       "interpretation": "Envelope membership alone does not establish historical consumption."})
                if seed in future_seen:
                    repeats.append({"current": key, "previous": future_seen[seed]})
                future_seen[seed] = key
                sample.append(row)
        future_collisions.extend(historical)
        bounded.append({"replica": vector["replica"], "offsets_per_slot": 512, "draws": len(sample),
                        "range_rule": "slot s: accepted324_offset[s] <= episode < accepted324_offset[s]+512",
                        "rows_canonical_sha256": digest(sample),
                        "new_cohort_hits": [r for r in sample if 0xD3000000 <= r["actual_seed"] <= 0xD30003FF],
                        "historical_observed_or_envelope_collisions": historical,
                        "within_or_cross_replica_collisions": repeats,
                        "limit": "finite arithmetic controls only; no guarantee beyond these indices or live reset patterns"})
    seeds = list(range(0xD3000000, 0xD3000400))
    cohort = {"study_id": STUDY_ID, "status": "proposed_unreserved_freshness_unproved",
              "purpose": "shared D2 normal-start full-run terminal evaluation; hexadecimal D300 is not difficulty D3",
              "inclusive_range": [seeds[0], seeds[-1]], "hex_range": ["0xD3000000", "0xD30003FF"],
              "count": 1024, "seeds": seeds, "seed_order": "ascending, shared across all seven policies",
              "seeds_canonical_sha256": digest(seeds),
              "seeds_u32be_sha256": hashlib.sha256(b"".join(s.to_bytes(4, "big") for s in seeds)).hexdigest(),
              "policies": "six predetermined global-update60 endpoints plus accepted324 once",
              "planned_episodes": 7168, "cutoff": "disabled, normal frame0 start, true death or ordinary18000 cap",
              "metrics": design["evaluation"], "authority": "none; collision evidence retains this proposal and blocks freshness; no silent replacement"}
    write("cohort.json", cohort)
    write("seed-vectors.json", {"schema": "progressive1000_proposed_rng_seed_vectors_v1", "status": "proposed_only_not_reserved_not_applied",
          "study_id": STUDY_ID, "vectors": vectors,
          "parent": {"integrity_receipt": PARENT, "integrity_receipt_sha256": PINNED[PARENT],
                     "checkpoint_sha256": parent["checkpoint_sha256"], "confirmation_acceptance_sha256": PINNED["learning/runs/v2/expanded-confirmation-parent-20261026-r1/parent-acceptance.json"],
                     "phase_update": 324, "cumulative_update": 372, "next_episode_indices": offsets},
          "derivation": {"domain": DOMAIN, "token_rule": "SHA256(DOMAIN|study=STUDY_ID|replica=i|stream=name|attempt=n)",
                         "field_rule": "first8 bytes big endian for env/u63; mask u63; first4 bytes for numpy/constructor; reject bounds and reserved/prior env masters",
                         "bounds": BOUNDS, "prior_masters_rejected": prior_masters,
                         "vector_hash_rule": "SHA256(canonical_json({study_id,replica,seeds})); sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False; arm excluded"},
          "pairing": "same complete vector for curriculum/control within replica; all six fields distinct across replicas; arithmetic domain separation does not prove stochastic independence",
          "arms": ["control_constant_3e-5", "progressive1000_curriculum_constant_3e-5"],
          "budget": "60 global updates per arm, accepted324 entity transformer/reward/KL unchanged",
          "initial_reference": "MISSING: separately measure independent CPU/MPS state digests for all three NEW vectors before actual restore; LR study accepted three-state references do not apply",
          "rng_access": "No policy/minibatch RNG read or draws. No invented independent minibatch or private NumPy Generator stream."})
    write("initial-slot-controls.json", {"status": "unexecuted_arithmetic_only", "replicas": initial})
    write("future-controls.json", {"status": "bounded_proposal_only", "replicas": bounded,
          "total_draws": 64 * 512 * 3, "entire_future_stream_covered": False,
          "parent_gate": "Pin actual full future bounds/reservations and enforce exclusion of all evaluation seeds before every construction/reset in both arms. Preserve/report repeated actual training seeds; do not silently change vectors."})
    write("proposed-exclusions.json", {"named_ranges": NAMED_RANGES, "canonical_sorted_merged_union": union,
          "canonical_union_sha256": digest(union), "installation_status": "not_installed",
          "both_arms": ["control", "curriculum"], "native_contract": "arbitrary inclusive additional ranges plus mandatory B; normalize/reject full coverage before construction; tuple rehash counter increments on excluded candidates",
          "frozen_exact_five_range_validator": "not changed; successor registration/validator must accept and pin the six-range canonical union",
          "parent_gate": "Verify effective native union, successor binary/source correspondence, preconstruction and reset rejection, complete future reservations. Static source and synthetic arithmetic are not runtime proof."})
    observed_hits = sorted(s for s in observed if seeds[0] <= s <= seeds[-1])
    envelope_hits = sorted(s for s in envelope if seeds[0] <= s <= seeds[-1])
    gaps = [
        "Historical known-consumed nonoverlap is NOT established: no closed inventory of every original environment construction, failed reset, unjournaled attempt, probe, benchmark and discarded branch.",
        "19 original training journals replayed; inclusive conservative slot envelopes include discarded updates and failed/aborted branches visible in journals, not unrecorded failed resets.",
        "Nested copied sources/provenance and synthetic fixtures are path-classified separately, never counted as real episodes; unresolved original-looking data remains a coverage gap.",
        "No qualification B/E outcome or run-seed content opened; only reserved B/E range constants used. Parent must preserve their closed status.",
        "Nonselected JSON, non-JSON logs, externally removed history, logs outside learning/runs/v2 and unrecorded native constructions are not covered.",
        "Prior lineage receipt validates ten checkpoint payloads historically; this task trusts its pinned receipt and performs no checkpoint deserialization or new checkpoint hashing.",
        "Future LR study/probe proposals and synthetic references do not prove actual episodes or new-study independent CPU/MPS references.",
        "All actual reservations, complete future stream coverage, exclusion installation and acceptance/launch authority remain parent gates.",
    ]
    if errors:
        gaps.append("Parse errors in scanned candidates remain unresolved; see coverage-map.json.")
    coverage = {"claim_status": "BLOCKED_PARTIAL_HISTORY_NO_FRESHNESS_AUTHORITY",
                "proposal_retained": True, "proposed_cohort_changed": False,
                "real_observed_unique_seed_values": len(observed), "original_logged_training_unique_seed_values": len(logged),
                "conservative_19_journal_envelope_unique_seed_values": len(envelope),
                "unresolved_provenance_unique_seed_values": len(unresolved),
                "proposal_or_unqualified_control_unique_seed_values": len(future),
                "real_observed_cohort_collisions": observed_hits,
                "conservative_envelope_cohort_collisions": envelope_hits,
                "all_collision_evidence": hits, "journal_replay_unmatched": unmatched,
                "record_counts_by_category": categories, "parse_errors": errors,
                "inventory_files": len(inventory), "files_opened": sum(x["opened"] for x in inventory),
                "path_categories": dict(collections.Counter(x["category"] for x in inventory)),
                "counts_meaning": "Unique u32 actual episode seed values, not independent episodes. Aggregate/log/copy duplicates cannot increase unique counts. Conservative generated envelope is separate from observations.",
                "known_coverage_gaps": gaps,
                "historical_future_control_intersections": len(future_collisions),
                "scope": "Current learning/runs/v2 path inventory and selected original-looking JSON/JSONL records, plus pinned prior lineage. No global-workspace freshness claim."}
    coverage["prior_lineage_known_missing_journal_directories"] = lineage["supplemental_scans"]["missing_journal_dirs"]
    coverage["prior_lineage_remaining_gaps"] = lineage["proof_boundary"]["remaining_gaps"]
    prior_audit = load("learning/runs/v2/expanded-evaluation-seed-exposure-audit-luna-20261026-r1/audit.json", "prior audit input reconciliation")
    inventory_by_path = {x["path"]: x for x in inventory}
    prior_comparison = []
    for row in prior_audit["source_hashes"]:
        path = row["path"]
        current = INPUTS.get(path)
        entry = inventory_by_path.get(path)
        prior_comparison.append({"path": path, "prior_sha256": row["sha256"],
                                 "current_sha256_if_opened": current["sha256"] if current else None,
                                 "current_category": entry["category"] if entry else "absent_from_path_inventory",
                                 "hash_unchanged_if_opened": current["sha256"] == row["sha256"] if current else None})
    write("prior-audit-input-reconciliation.json", {"prior_source_count": len(prior_comparison),
          "files": prior_comparison,
          "scope": "Hash comparison only for opened current inputs; skipped copies/fixtures are not reclassified as real observations."})
    write("coverage-map.json", coverage)
    write("observed-seeds.json", {"real_observed_sorted_unique_seeds": sorted(observed),
          "real_observed_seeds_canonical_sha256": digest(sorted(observed)),
          "conservative_envelope_sorted_unique_seeds": sorted(envelope),
          "conservative_envelope_seeds_canonical_sha256": digest(sorted(envelope))})
    write("input-manifest.json", {"schema": "stdlib_read_hash_manifest_v1", "inputs": list(sorted(INPUTS.values(), key=lambda x: x["path"])),
          "explicit_expected_pins": PINNED, "checkpoint_binary_reads": 0,
          "qualification_content_reads": 0, "cache_empty": not any((HERE / "empty-pycache").iterdir())})
    print(json.dumps({k: coverage[k] for k in ("real_observed_unique_seed_values", "real_observed_cohort_collisions", "conservative_envelope_cohort_collisions", "files_opened", "inventory_files", "historical_future_control_intersections")}), flush=True)


if __name__ == "__main__":
    main()
