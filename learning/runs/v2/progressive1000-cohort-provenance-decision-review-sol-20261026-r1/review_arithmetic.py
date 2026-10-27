"""Read-only stdlib source/metadata review; all writes remain beside this file.

Does not import project modules, read checkpoints, execute campaign code, or
open expected-result tables. Archive reads use an explicit member allowlist.
"""
import ast
import hashlib
import json
import pathlib
import re
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).resolve().parent
RUNS = ROOT / "learning/runs/v2"
R1 = "progressive1000-seed-cohort-prepare-sol-20261026-r1"
R2 = "progressive1000-seed-history-closure-sol-20261026-r2"
PINS = {}
MEMBERS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def read(relative):
    assert not any(s in relative.lower() for s in
                   ("expected", "episodes.jsonl", "results-summary", "baseline-replay", "baseline-selection"))
    path = ROOT / relative
    raw = path.read_bytes()
    PINS[relative] = {"sha256": sha(raw), "bytes": len(raw)}
    return raw


def load(group, name):
    return json.loads(read(f"learning/runs/v2/{group}/{name}"))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def archive_sources(group, archive, members):
    # Hash archive bytes without decompressing other members. Never extract files.
    relative = f"learning/runs/v2/{group}/{archive}"
    read(relative)
    result = {}
    with tarfile.open(ROOT / relative) as handle:
        for member in members:
            assert "expected" not in member.lower()
            raw = handle.extractfile(member).read()
            text = raw.decode()
            lines = text.splitlines()
            selected = [[i, line] for i, line in enumerate(lines, 1)
                        if re.search(r"^(use |import |from |fn |def |pub enum PolicyKind|pub struct Policy|#\[path)|"
                                     r"PolicyKind::|Policy::new|const SEEDS|for seed in|"
                                     r"let actions|actions\s*=|checkpoint|torch|load_state|"
                                     r"Command::|subprocess|members =|crates/dodge", line)]
            row = {"archive": relative, "member": member, "sha256": sha(raw),
                   "bytes": len(raw), "source_lines": selected}
            if member.endswith("test_env.py"):
                tree = ast.parse(text)
                row["imports"] = [ast.unparse(n) for n in ast.walk(tree)
                                  if isinstance(n, (ast.Import, ast.ImportFrom))]
                row["call_targets"] = sorted({ast.unparse(n.func) for n in ast.walk(tree)
                                               if isinstance(n, ast.Call)})
            MEMBERS.append(row)
            result[member] = text
    return result


def command_rows(group, name):
    raw = read(f"learning/runs/v2/{group}/{name}")
    rows = [json.loads(line) for line in raw.decode().splitlines()] if name.endswith("jsonl") else [json.loads(raw)]
    return [{key: value for key, value in row.items()
             if key in ("command", "argv", "exit_code", "name", "label", "cwd", "log")}
            for row in rows]


cohort_raw = read(f"learning/runs/v2/{R1}/cohort.json")
vectors_raw = read(f"learning/runs/v2/{R1}/seed-vectors.json")
assert sha(cohort_raw) == "dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45"
assert sha(vectors_raw) == "698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf"
cohort = json.loads(cohort_raw)
vectors = json.loads(vectors_raw)
seeds = set(cohort["seeds"])
assert cohort["seeds"] == list(range(0xD3000000, 0xD3000400))
assert len(seeds) == 1024 and cohort["planned_episodes"] == 7 * 1024 == 7168

observed = load(R2, "observed-seeds.json")
additional = load(R2, "additional-observed-seeds.json")
merged = load(R2, "merged-conservative-seeds.json")
fixed = load(R2, "fixed-list-coverage.json")
campaigns = load(R2, "campaign-closure.json")
extra = load(R2, "additional-construction-coverage.json")
six = load(R2, "six-directory-closure.json")
exclusions = load(R2, "proposed-exclusions.json")
gaps = load(R2, "remaining-gap-register.json")
lineage = load("expanded-seed-lineage-parent-validation-20261026-r5", "receipt.json")
incident = load(R2, "boundary-incident.json")  # Metadata only; no quoted results.
load(R2, "d3-no-attempt.json")
load(R2, "97593849-reconciliation.json")
load(R2, "cohort-collision-check.json")
load(R2, "future-merged-recheck.json")
load("progressive1000-seed-r1-parent-validation-20261026-r1", "receipt.json")
# This file was encountered during initial attribution outside this helper.
# Pin bytes only here; no result-field parsing or use in the proof.
read("learning/runs/v2/milestone1-r2/benchmark-provenance.json")

old_observed = set(observed["real_observed_sorted_unique_seeds"])
all_observed = old_observed | set(additional["new_sorted_unique_seed_values"])
envelope = set(observed["conservative_envelope_sorted_unique_seeds"])
all_possible = set(merged["sorted_unique_seed_values"])
assert (len(old_observed), len(all_observed), len(envelope), len(all_possible)) == (87430, 87579, 164385, 189743)
assert sha(canonical(sorted(all_possible))) == merged["canonical_sha256"]
assert not seeds & (all_observed | all_possible)

# Independent tuple arithmetic, transcribed from pinned Rust seed.rs. No imports
# from preparation/control modules and no native/environment construction.
MASK = (1 << 64) - 1
HIST = [(0xB0000000, 0xB00003E7), (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7)]
UNION = exclusions["canonical_sorted_merged_union"]


def mix(value):
    value &= MASK
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK
    return value ^ (value >> 31)


def derive(master, slot, episode, ranges):
    base = (mix(master ^ 0x444F4447455F5632)
            ^ mix(slot + 0x9E3779B97F4A7C15)
            ^ mix(episode + 0xD1B54A32D192ED03))
    for counter in range(4096):
        value = mix(base ^ mix(counter + 0x94D049BB133111EB)) >> 32
        if not any(lo <= value <= hi for lo, hi in ranges):
            return value, counter
    raise AssertionError("arithmetic rejection budget exhausted")


def interval(master, starts, ends, ranges):
    assert len(starts) == len(ends)
    return {derive(master, slot, episode, ranges)[0]
            for slot, (start, end) in enumerate(zip(starts, ends))
            for episode in range(start, end + 1)}


read("crates/dodge-rl-env/src/seed.rs")
read("crates/dodge-rl-env/src/config.rs")
tight = set()
bounds = []
for row in campaigns:
    values = interval(row["master"], row["initial_episode_indices"],
                      row["possible_inclusive_episode_end"], HIST)
    assert len(values) == row["finite_unique_interval_seeds"]
    assert values <= all_possible
    tight |= values
    bounds.append({key: row[key] for key in
                   ("campaign", "master", "initial_episode_indices", "possible_inclusive_episode_end",
                    "bound_basis", "finite_unique_interval_seeds")})
    bounds[-1]["cohort_collisions"] = sorted(values & seeds)
for row in extra:
    ranges = [(0xB0000000, 0xB00003E7)] if row["campaign"].endswith("milestone2-wrapper-r1") else HIST
    values = interval(row["master"], row["initial_episode_indices"], row["possible_inclusive_episode_end"], ranges)
    assert values <= all_possible
    tight |= values
for row in six:
    if row.get("classification") == "real_training_mode_validation_not_optimizer_training":
        values = interval(row["master"], row["initial_episode_indices"], row["possible_inclusive_episode_end"], HIST)
        assert values <= all_possible
        tight |= values
assert len(tight) == 89959
assert envelope | tight | set(fixed["possible_seed_values"]) | all_observed == all_possible
assert len(UNION) == 6 and sha(canonical(UNION)) == exclusions["canonical_union_sha256"]
assert all(any(lo <= seed <= hi for lo, hi in UNION) for seed in seeds)

future_intersections = []
future_cohort_hits = []
future_seen = set()
future_duplicates = []
for vector in vectors["vectors"]:
    for slot, start in enumerate(vectors["parent"]["next_episode_indices"]):
        for episode in range(start, start + 512):
            value, counter = derive(vector["seeds"]["env_master_seed"], slot, episode, UNION)
            point = {"replica": vector["replica"], "slot": slot, "episode": episode,
                     "counter": counter, "actual_seed": value}
            if value in all_possible:
                future_intersections.append({**point, "observed_historical": value in all_observed,
                                             "tight_known_attempt": value in tight})
            if value in seeds:
                future_cohort_hits.append(point)
            if value in future_seen:
                future_duplicates.append(point)
            future_seen.add(value)
assert len(future_seen) == 98304 and not future_cohort_hits and not future_duplicates
assert len(future_intersections) == 1 and future_intersections[0]["actual_seed"] == 97593849
assert derive(4200000000, 44, 48, HIST)[0] == 97593849

command_evidence = {}
for group, names in {
    "milestone1-r1": ["benchmark-receipt.json", "test-workspace-final.json"],
    "milestone1-r2": ["test-workspace.json"],
    "milestone2-core-r1": ["test-workspace.json", "targeted-initial.json", "targeted-exhaustion.json",
                           "before-profile.json", "after-profile.json", "before-layout-run.json", "after-layout-run.json"],
    "milestone2-binding-r1": ["commands.jsonl"],
    "milestone2-math-r1": ["commands.jsonl"],
    "milestone2-wrapper-r1": ["commands.jsonl"],
}.items():
    command_evidence[group] = {name: command_rows(group, name) for name in names}

for group, archive, members in [
    ("milestone1-r1", "source.tar.gz", ["Cargo.toml", "crates/dodge-core/examples/headless_profile.rs"]),
    ("milestone1-r2", "source.tar.gz", ["crates/dodge-core/examples/headless_profile.rs"]),
    ("milestone2-core-r1", "source.tar.gz", ["Cargo.toml", "crates/dodge-core/Cargo.toml",
       "crates/dodge-native-runner/Cargo.toml", "crates/dodge-viewer/Cargo.toml",
       "crates/dodge-core/examples/headless_profile.rs"]),
    ("milestone2-wrapper-r1", "source.tar.gz", ["crates/dodge-rl-env/Cargo.toml", "crates/dodge-rl-env/src/lib.rs",
       "crates/dodge-rl-env/src/tests.rs", "crates/dodge-rl-env/tests/support/m0_policy.rs"]),
    ("milestone2-binding-r1", "source-final.tar.gz", ["crates/dodge-rl-env/Cargo.toml", "python/tests/test_env.py",
       "crates/dodge-rl-env/src/tests.rs", "crates/dodge-rl-env/tests/support/m0_policy.rs"]),
]:
    archive_sources(group, archive, members)

for group in ("milestone1-r1", "milestone1-r2", "milestone2-core-r1", "milestone2-wrapper-r1", "milestone2-math-r1"):
    load(group, "source-manifest.json")
load("milestone2-binding-r1", "owned-source-manifest.json")
for relative in ("learning/runs/v2/milestone2-wrapper-r1/trajectory_probe.rs",
                 "learning/runs/v2/milestone2-math-r1/fixtures.rs",
                 "learning/runs/v2/milestone2-math-r1/frozen/geometry.rs",
                 "learning/runs/v2/milestone2-math-r1/frozen/raster.rs",
                 "learning/runs/v2/milestone2-core-r1/layout_probe.rs",
                 "python/dodge_rl/train_teacher.py", "learning/python/dodge_learning/seeds.py"):
    read(relative)

gate_identity = load("gate-baselines-r1", "pre-d3-identity.json")
gate_sources = {}
for relative in ("learning/.cache/v2-m0-review-r2/crates/dodge-core/examples/m0_baseline.rs",
                 "learning/.cache/v2-m0-review-r2/crates/dodge-core/examples/m0/policy.rs"):
    raw = read(relative)
    native_relative = relative.split("v2-m0-review-r2/", 1)[1]
    assert sha(raw) == gate_identity["harness_doc_sha256"][native_relative]
    gate_sources[relative] = {"sha256": sha(raw), "source_lines":
        [[i, line] for i, line in enumerate(raw.decode().splitlines(), 1)
         if re.search(r"const SEED_BASE|fn run_baselines|for kind in PolicyKind::ALL|"
                      r"for index in 0\.\.options.episodes|Episode::run\(kind|Policy::new|"
                      r"pub enum PolicyKind|pub const ALL|PolicyKind::Random =>|"
                      r"PolicyKind::Neutral =>|PolicyKind::AabbDodger =>", line)]}
for name in ("audit_gate.py", "run_gate.py"):
    read(f"learning/runs/v2/gate-baselines-r1/{name}")

roles = {
    "gate-baselines-r1": ("native_heuristic_baseline", "Pinned m0_baseline runs Random, Neutral, AabbDodger; fixed B base plus index. D1/D3 are native difficulty settings. No learned checkpoint, optimizer, or teacher-selection evaluation."),
    "milestone1-r1": ("core_renderer_unit_tests_and_fixed_random_profile", "Workspace contains core, native runner, viewer; headless_profile uses PicoRng actions and seeds 1000..1063. No learned teacher entrypoint."),
    "milestone1-r2": ("core_renderer_unit_tests", "Same workspace and profile source identity as r1; command selects native workspace tests. No learned teacher entrypoint."),
    "milestone2-core-r1": ("core_observation_tests_random_profile_and_layout", "Native workspace and observation_tests; profile uses fixed random schedules; layout prints size_of types. No learned teacher entrypoint."),
    "milestone2-binding-r1": ("binding_contract_and_gil_tests", "Rust wrapper tests and pytest test_env.py exercise environment schemas, arrays, seed/reset metadata and GIL behavior. Python imports only ctypes/sys/threading/time/numpy/pytest and environment binding. No learned model/checkpoint or optimizer call."),
    "milestone2-math-r1": ("pure_geometry_raster_fixtures", "rustc --test fixtures.rs includes only geometry/raster primitives. No environment or learner entrypoint."),
    "milestone2-wrapper-r1": ("wrapper_contract_renderer_heuristic_replay_and_arithmetic_actions", "Rust wrapper tests; explicit ignored replay uses the same three hand-written policies. Supplemental trajectory uses (decision*7+slot*3)%9. Training seed mode is seed generation, not fitting a teacher."),
}
classification = []
for group in gaps["groups"]:
    category, reason = roles[group["id"]]
    classification.append({"group": group["id"], "file_roles": group["path_count"],
                           "classification": category, "learned_teacher_exposure": False,
                           "reason": reason, "decision": "not_a_teacher_freshness_blocker",
                           "limit": "This closes the named group's role, not global never-simulated seed history."})
assert sum(row["file_roles"] for row in classification) == 122

write("group-classification.json", classification)
write("source-evidence.json", {"archive_members": MEMBERS, "gate_sources": gate_sources,
                                "gate_native_identity": {k: gate_identity[k] for k in
                                  ("head", "worktree", "executable_sha256", "harness_doc_sha256")},
                                "original_commands": command_evidence})
write("campaign-bounds.json", bounds)
write("arithmetic-receipt.json", {
    "proposal_sha256": sha(cohort_raw), "vectors_sha256": sha(vectors_raw),
    "cohort": [hex(min(seeds)), hex(max(seeds))], "cohort_count": len(seeds), "planned_episodes": 7168,
    "observed_R1": len(old_observed), "observed_R2_merged": len(all_observed),
    "R1_zero_origin_envelope": len(envelope), "tight_known_attempt_values": len(tight),
    "fixed_possible_values": len(fixed["possible_seed_values"]), "merged_possible_values": len(all_possible),
    "merged_values_canonical_sha256": merged["canonical_sha256"],
    "cohort_observed_hits": sorted(seeds & all_observed), "cohort_conservative_hits": sorted(seeds & all_possible),
    "campaign_bounds_independently_recomputed": len(bounds),
    "future_inclusive_union": UNION, "future_union_sha256": exclusions["canonical_union_sha256"],
    "future_installation_status_in_pinned_proposal": exclusions["installation_status"],
    "future_draws": len(future_seen), "future_cohort_hits": future_cohort_hits,
    "future_training_intersections": future_intersections, "future_duplicates": future_duplicates,
    "full_future_stream_enumerated": False,
    "seed_97593849_historical_origin": {"master": 4200000000, "slot": 44, "episode": 48,
       "actual_construction_start_episode": 262, "consumed": False,
       "basis": "R2 lifecycle bound; prefix membership alone is not consumption."},
})
write("incident-metadata.json", {
    "source": f"learning/runs/v2/{R2}/boundary-incident.json",
    "prior_qualification_content_isolation_passed": incident["qualification_content_isolation_passed"],
    "prior_incidents": incident["incidents"],
    "separate_from_collision_proof": True, "outcome_values_used_or_quoted": False,
    "this_review_expected_table_or_qualification_outcome_reads": 0,
    "this_review_nonqualification_result_field_exposure": {
        "path": "learning/runs/v2/milestone1-r2/benchmark-provenance.json",
        "context": "initial command/source attribution", "values_used_or_reproduced": False,
        "strict_all_content_outcome_free_claim": False},
    "decision": "Parent owns incident response; preserve qualification closure, no automatic replacement."})
assembly = "progressive1000-shared-runtime-assembly-sol-20261026-r1"
successor = {"source_only": True, "runtime_enforcement_qualified_by_this_review": False,
             "templates": [], "source": {}}
for name in ("transition.py", "contracts.py", "runtime_adapter.py"):
    raw = read(f"learning/runs/v2/{assembly}/{name}")
    successor["source"][name] = {"sha256": sha(raw), "source_lines":
        [[i, line] for i, line in enumerate(raw.decode().splitlines(), 1)
         if any(token in line for token in ("EXPECTED_EXCLUSION_RANGES", "at least six", "len(normalized)<6",
                                            "def make_env", "controls = c.episode_controls",
                                            "excluded_seed_ranges=", "self.env = self.game.VecDodgeEnv"))]}
for vector in vectors["vectors"]:
    for arm in vectors["arms"]:
        name = f"registration-template-replica-{vector['replica']}-{arm}.json"
        registration = load(assembly, name)
        assert registration["exclusion_union"] == UNION
        assert registration["vector"] == vector
        successor["templates"].append({"path": f"learning/runs/v2/{assembly}/{name}",
                                       "arm": arm, "replica": vector["replica"],
                                       "status": registration["status"], "union_matches": True,
                                       "proposal_vector_matches": True})
write("successor-exclusion-source.json", successor)
write("input-pins.json", PINS)
write("receipt.json", {
    "status": "ACCEPT_RECOMMENDATION_FOR_RECORDED_ACCEPTED324_TEACHER_HISTORY_SCOPE",
    "parent_owns_decision": True, "remaining_named_group_teacher_bound_blockers": [],
    "groups_classified": len(classification), "file_roles_classified": 122,
    "proposal_or_vectors_changed": False, "reservation_or_registration_writes": 0,
    "project_runtime_imports": 0, "model_or_environment_constructions": 0,
    "checkpoint_reads_or_deserializations": 0, "Torch_NumPy_native_MPS_calls": 0,
    "training_evaluation_probe_runs": 0, "subdelegations": 0, "commits_pushes": 0,
    "qualification_outcomes_or_expected_tables_opened": 0,
    "strict_all_content_outcome_free_claim": False,
    "nonqualification_benchmark_result_field_exposure": "incident-metadata.json",
    "retained_setup_failure": "Initial arithmetic script stopped at zip(strict=True), unsupported by host python3; corrected to explicit length equality plus zip. No runtime/campaign was invoked.",
    "writes_outside_owned_output": 0,
    "limit": "Recorded accepted324 entity-teacher lineage, related recorded attempts and checkpoint selection/evaluation; no global workspace never-used or every unrelated teacher claim. Future exclusion enforcement still requires successor wiring.",
    "lineage_receipt_parent_links_verified": lineage["parent_links_verified"],
    "lineage_receipt_root_parent": lineage["parent_link_records"][0],
})
print(json.dumps({"groups": len(classification), "file_roles": 122,
                  "observed": len(all_observed), "conservative": len(all_possible),
                  "cohort_hits": 0, "future_draws": len(future_seen), "status": "review_written"}))
