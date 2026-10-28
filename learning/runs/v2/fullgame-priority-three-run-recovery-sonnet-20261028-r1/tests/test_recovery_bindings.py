"""Stdlib CPU/fake checks for the three-run seed-priority recovery packet.

Read-only against accepted inputs. No native, torch, checkpoint, MPS, training or
reference execution. Fixtures live in a temporary directory inside this package.
"""
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PKG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PKG)]
import remaining_plan as p
import start_remaining_one as launcher
import power_guard
import datetime
import watch_progress as monitor
import seed_priority as sp  # resolved from the r3 source via the launcher import

b = launcher.b
TMP_ROOT = PKG / "tmp"
RUNS = [p.run_id(*key) for key in p.REMAINING]


def candidate(replica, arm):
    return p.read(p.run_home(replica, arm) / "registration-final-candidate.json")


class Identity(unittest.TestCase):
    def test_first_run_finalization_reproduced_byte_exact(self):
        draft = p.read(p.DRAFT_DIR / "replica-1-uniform.json")
        first = p.to_candidate(draft, p.FIRST_HOME, p.FIRST_OWNER_TOKEN, "fullgame_seed_priority_fresh_attempt")
        self.assertEqual(hashlib.sha256(p.dump(first)).hexdigest(), p.FIRST_REGISTRATION_SHA256)
        self.assertEqual(p.sha(p.FIRST_HOME / "registration-final.json"), p.FIRST_REGISTRATION_SHA256)

    def test_immutable_pins_unchanged(self):
        self.assertEqual(p.sha(p.R3 / "source-manifest.json"), p.SOURCE_MANIFEST_SHA256)
        self.assertEqual(p.sha(p.R3 / "runtime-manifest.json"), p.RUNTIME_MANIFEST_SHA256)
        self.assertEqual(p.sha(p.SOURCE_ACCEPTANCE), p.SOURCE_ACCEPTANCE_SHA256)
        self.assertEqual(p.sha(p.FIRST_HOME / "parent-terminal-audit.json"), p.FIRST_AUDIT_SHA256)
        for key, digest in p.DRAFT_SHA256.items():
            self.assertEqual(p.sha(p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json"), digest)

    def test_recovery_set_is_exactly_three_and_excludes_completed(self):
        self.assertEqual(RUNS, [p.run_id(2, "opening_priority"), p.run_id(3, "uniform"), p.run_id(3, "opening_priority")])
        done = {p.run_id(r, a) for r, a, _ in p.COMPLETED} | {p.FIRST_RUN_ID}
        self.assertFalse(done & set(RUNS))
        self.assertEqual(set(p.REMAINING) | {(r, a) for r, a, _ in p.COMPLETED} | {(1, "uniform")}, set(p.DRAFT_SHA256))

    def test_failure_and_checkpoint_evidence_unchanged(self):
        self.assertEqual(p.sha(p.FAILURE / "audit.json"), p.FAILURE_AUDIT_SHA256)
        self.assertEqual(p.sha(p.FAILURE / "lease-release.json"), p.FAILURE_RELEASE_SHA256)
        self.assertEqual(p.sha(p.CHECKPOINT), p.CHECKPOINT_SHA256)
        self.assertEqual(p.sha(p.PARENT_RECEIPT), p.PARENT_RECEIPT_SHA256)
        for key, digest in p.OLD_CANDIDATE_SHA256.items():
            self.assertEqual(p.sha(p.PARENT_PKG / p.run_id(*key) / "registration-final-candidate.json"), digest)


class Candidates(unittest.TestCase):
    def test_candidates_are_unedited_transforms_of_reviewed_drafts(self):
        for key in p.REMAINING:
            reg = candidate(*key)
            draft = p.read(p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json")
            rebuilt = p.to_candidate(draft, p.run_home(*key), reg["expected_lease"]["owner_token"], p.LEASE_KIND)
            self.assertEqual(p.dump(rebuilt), (p.run_home(*key) / "registration-final-candidate.json").read_bytes())

    def test_each_candidate_passes_r3_static_contract(self):
        contracts = b._contracts()
        for key in p.REMAINING:
            reg = candidate(*key)
            contracts.validate_static(reg, startup=False)

    def test_frozen_budgets_and_lineage(self):
        for key in p.REMAINING:
            reg = candidate(*key)
            self.assertEqual(reg["limits"], dict(work_seconds=3780, total_seconds=3790, cleanup_seconds=10,
                rss_bytes=6 * 1024 ** 3, mps_bytes=6 * 1024 ** 3, raw_frames=16712512, resets=983040, retries=0))
            self.assertEqual(reg["limits"]["resets"], 64 * 256 * 60)
            self.assertEqual((reg["shared_config"]["batch_size"], reg["shared_config"]["rollout_steps"],
                              reg["shared_config"]["global_updates"], reg["schedule"]["updates"]), (64, 256, 60, 60))
            self.assertEqual(reg["ppo"]["learning_rate"], 3e-5)
            self.assertEqual(reg["shared_config"]["environment"], dict(action_repeat=4, cutoff_enabled=False,
                difficulty=2, normal_start=True, patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000))
            self.assertEqual(reg["parent_checkpoint_sha256"], p.CHECKPOINT_SHA256)
            self.assertEqual(reg["source_manifest_sha256"], p.SOURCE_MANIFEST_SHA256)
            self.assertEqual(reg["runtime_manifest_sha256"], p.RUNTIME_MANIFEST_SHA256)
            self.assertEqual(reg["backend"], "mps")
            self.assertEqual(reg["future_evaluation_cohorts"], ["D4", "D5"])
            self.assertEqual(reg["native_seed_mode"], {"mode": "evaluation", "meaning": "explicit_seed_list"})
            self.assertEqual(reg["training_pool_role"], "training_only")
            self.assertEqual(reg["schedule"]["candidate_selection"], False)
            self.assertEqual(reg["schedule"]["promotion"], False)
            self.assertEqual(reg["expected_lease"]["MPS_driver_bytes"], 6442450944)
            self.assertEqual(reg["expected_lease"]["RSS_bytes"], 6442450944)

    def test_run_paths_private_unspent_and_not_reused(self):
        seen = set()
        for key in p.REMAINING:
            reg, home = candidate(*key), p.run_home(*key)
            for field, name in (("output", "worker-output"), ("attempt_claim_path", "attempt.claimed"),
                                ("launch_marker_path", "launch.claimed")):
                self.assertEqual(Path(reg[field]), home / name)
                self.assertFalse(Path(reg[field]).exists())
                self.assertNotIn(reg[field], seen)
                seen.add(reg[field])
            cache = Path(reg["import_policy"]["pycache_prefix"])
            self.assertEqual(cache, home / "empty-pycache")
            self.assertTrue(cache.is_dir() and not any(cache.iterdir()))
            self.assertNotIn("/fullgame-seed-priority-experiment-luna-20261027-r3/attempts", reg["attempt_claim_path"])
            self.assertTrue(str(home).startswith(str(p.HERE)))
        tokens = [candidate(*key)["expected_lease"]["owner_token"] for key in p.REMAINING]
        old = [p.read(p.PARENT_PKG / p.run_id(*key) / "registration-final-candidate.json")["expected_lease"]["owner_token"]
               for key in p.REMAINING]
        self.assertEqual(len(set(tokens + old + [p.FIRST_OWNER_TOKEN])), 7)
        self.assertEqual({candidate(*key)["expected_lease"]["kind"] for key in p.REMAINING}, {p.LEASE_KIND})

    def test_only_private_paths_and_lease_differ_from_parent_package_registrations(self):
        for key in p.REMAINING:
            new = candidate(*key)
            old = p.read(p.PARENT_PKG / p.run_id(*key) / "registration-final-candidate.json")
            differing = {k for k in set(new) | set(old) if new.get(k) != old.get(k)}
            self.assertEqual(differing, {"output", "attempt_claim_path", "launch_marker_path", "import_policy", "expected_lease"})
            for field in ("output", "attempt_claim_path", "launch_marker_path"):
                self.assertNotEqual(new[field], old[field])
                self.assertFalse(new[field].startswith(str(p.PARENT_PKG)))
            self.assertEqual(new["run_id"], old["run_id"])
            self.assertEqual((new["vector"], new["pair_id"], new["parent_checkpoint_sha256"]),
                             (old["vector"], old["pair_id"], old["parent_checkpoint_sha256"]))

    def test_candidates_reference_r3_only(self):
        for key in p.REMAINING:
            text = (p.run_home(*key) / "registration-final-candidate.json").read_text()
            self.assertNotIn("experiment-luna-20261027-r2", text)
            self.assertNotIn("experiment-luna-20261027-r1", text)
            self.assertIn("experiment-luna-20261027-r3", text)

    def test_pool_disjoint_from_exclusions_and_d4_d5_unopened(self):
        reg = candidate(2, "opening_priority")
        pool = sp.validate_pool(p.read(reg["training_pool_path"]))
        registry = p.read(p.PROGRAMME / "seed-priority-parent-registry.json")
        self.assertEqual(reg["parent_registry_sha256"], p.sha(p.PROGRAMME / "seed-priority-parent-registry.json"))
        self.assertEqual(pool["pool_sha256"], registry["pool_sha256"])
        for lo, hi in registry["exclusion_union"]:
            self.assertFalse(any(lo <= seed <= hi for seed in pool["all"]))
        for name, (lo, hi) in registry["future_evaluation_ranges"].items():
            self.assertIn([lo, hi], reg["exclusion_union"], name)


class PairingAndStreams(unittest.TestCase):
    def test_pairs_differ_only_in_declared_fields_and_lease_bookkeeping(self):
        declared = set(b._contracts().PAIR_DIFF_FIELDS)
        completed_uniform = p.PARENT_PKG / p.run_id(2, "uniform") / "registration-final.json"
        pairs = {2: (p.read(completed_uniform), candidate(2, "opening_priority")),
                 3: (candidate(3, "uniform"), candidate(3, "opening_priority"))}
        for replica, (uniform, priority) in pairs.items():
            self.assertEqual((uniform["arm"], priority["arm"]), ("uniform", "opening_priority"))
            different = {k for k in set(uniform) | set(priority) if uniform.get(k) != priority.get(k)}
            self.assertEqual(different - declared, {"expected_lease", "import_policy"}, replica)
            for field in ("vector", "reference", "reference_approval", "initial_episode_indices", "pair_id",
                          "training_pool_sha256", "exclusion_union", "ppo", "shared_config", "schedule", "limits",
                          "parent_registry_sha256", "source_manifest_sha256", "runtime_manifest_sha256"):
                self.assertEqual(uniform[field], priority[field], field)
            self.assertEqual({k: v for k, v in uniform["expected_lease"].items()
                              if k not in {"arm", "run_id", "owner_token", "kind"}},
                             {k: v for k, v in priority["expected_lease"].items()
                              if k not in {"arm", "run_id", "owner_token", "kind"}})

    def test_replica_vectors_and_audited_references_reused_not_rerun(self):
        vectors = p.read(p.R3 / "seed-vectors.json")["vectors"]
        for key in p.REMAINING:
            reg = candidate(*key)
            replica = key[0]
            self.assertEqual(reg["vector"], vectors[replica - 1])
            ref = p.REF_ROOT / "outputs" / f"replica-{replica}.json"
            approval = p.REF_ROOT / f"reference-approval-replica-{replica}.json"
            self.assertEqual(reg["reference"]["receipt_path"], str(ref))
            self.assertEqual(reg["reference"]["receipt_sha256"], p.sha(ref))
            self.assertEqual(reg["reference_approval"], {"path": str(approval), "sha256": p.sha(approval)})
            self.assertEqual(reg["reference"]["vector_sha256"], vectors[replica - 1]["vector_sha256"])

    def test_independent_stream_recomputation_matches_for_sampled_slots(self):
        for key in p.REMAINING:
            reg = candidate(*key)
            pool = sp.validate_pool(p.read(reg["training_pool_path"]))
            for slot in (0, 31, 63):
                entries = sp.sequence_entries(pool, study_id=p.STUDY, replica=key[0],
                    env_master_seed=reg["vector"]["seeds"]["env_master_seed"], arm=key[1], slot=slot,
                    count=reg["initial_episode_indices"][slot] + sp.EPISODES_PER_SLOT)
                self.assertEqual(sp.stream_digest([s for s, _ in entries]), reg["slot_stream_sha256"][slot])
                self.assertEqual(sp.stream_digest([c for _, c in entries]), reg["slot_component_sha256"][slot])

    def test_priority_expected_hard_share_and_shared_uniform_floor(self):
        reg = candidate(2, "opening_priority")
        pool = sp.validate_pool(p.read(reg["training_pool_path"]))
        hard = set(pool["hard"])
        common = dict(study_id=p.STUDY, replica=2, env_master_seed=reg["vector"]["seeds"]["env_master_seed"], slot=0,
                      count=sp.EPISODES_PER_SLOT)
        priority = sp.sequence_entries(pool, arm="opening_priority", **common)
        uniform = sp.sequence_entries(pool, arm="uniform", **common)
        share = sum(seed in hard for seed, _ in priority) / len(priority)
        self.assertAlmostEqual(share, 0.75, delta=0.02)
        self.assertAlmostEqual(sum(seed in hard for seed, _ in uniform) / len(uniform), 0.5, delta=0.02)
        floor = [i for i, (_, c) in enumerate(priority) if c == "uniform_floor"]
        self.assertTrue(floor)
        self.assertTrue(all(priority[i][0] == uniform[i][0] for i in floor))
        self.assertAlmostEqual(reg["priority"]["sampling_probability"]["relative_cap"], 1.5)
        self.assertEqual(reg["priority"]["uniform_floor"], 0.5)


class ProspectivePacket(unittest.TestCase):
    def test_no_authority_artifacts_exist(self):
        for name in ("registration-index.json", "parent-gates.json", "fresh-user-authorization.json"):
            self.assertFalse((p.HERE / name).exists(), name)
        for key in p.REMAINING:
            home = p.run_home(*key)
            self.assertFalse((home / "registration-final.json").exists())
            self.assertEqual(sorted(x.name for x in home.iterdir()),
                             ["empty-pycache", "registration-final-candidate.json"])

    def test_proposal_documents_are_visibly_prospective(self):
        index = p.read(p.HERE / "registration-index-proposal.json")
        gates = p.read(p.HERE / "parent-gates-proposal.json")
        self.assertEqual(index["status"], p.INDEX_PROPOSAL_STATUS)
        self.assertIs(index["launch_authority"], False)
        self.assertEqual(index["user_approval"], "NOT_GIVEN")
        self.assertEqual(gates["status"], p.GATES_PROPOSAL_STATUS)
        self.assertIs(gates["launch_authority"], False)
        self.assertTrue(gates["authorization"].startswith("NOT AUTHORIZED"))
        self.assertEqual([r["run_id"] for r in index["runs"]], RUNS)
        for row in index["runs"]:
            self.assertEqual(p.sha(row["registration_candidate"]), row["registration_sha256"])
            self.assertNotEqual(row["registration_sha256"], row["superseded_registration_sha256"])
            self.assertFalse(Path(row["registration"]).exists())
        self.assertEqual(gates["registration_index_proposal_sha256"], p.sha(p.HERE / "registration-index-proposal.json"))
        self.assertEqual(gates["pins"][str(p.HERE / "registration-index-proposal.json")], gates["registration_index_proposal_sha256"])

    def test_gate_pins_bind_failure_checkpoint_candidates_and_exclude_stale_authority(self):
        gates = p.read(p.HERE / "parent-gates-proposal.json")
        for path, digest in gates["pins"].items():
            self.assertEqual(p.sha(path), digest, path)
        names = {Path(path).name for path in gates["pins"]}
        self.assertNotIn("state.json", names)
        self.assertIn("seed-history-ledger-snapshot.json", names)
        for stale in p.STALE_AUTHORITY:
            self.assertNotIn(str(stale), gates["pins"], stale)
        self.assertFalse(any("experiment-luna-20261027-r2" in path for path in gates["pins"]))
        self.assertFalse(any(path.startswith(str(p.PARENT_PKG)) and Path(path).suffix == ".json"
                             and "registration-final-candidate" in path for path in gates["pins"]))
        pins = gates["pins"]
        self.assertEqual(pins[str(p.R3 / "source-manifest.json")], p.SOURCE_MANIFEST_SHA256)
        self.assertEqual(pins[str(p.R3 / "runtime-manifest.json")], p.RUNTIME_MANIFEST_SHA256)
        self.assertEqual(pins[str(p.FAILURE / "audit.json")], p.FAILURE_AUDIT_SHA256)
        self.assertEqual(pins[str(p.FAILURE / "lease-release.json")], p.FAILURE_RELEASE_SHA256)
        self.assertEqual(pins[str(p.CHECKPOINT)], p.CHECKPOINT_SHA256)
        self.assertEqual(pins[str(p.PARENT_RECEIPT)], p.PARENT_RECEIPT_SHA256)
        self.assertEqual(pins[str(p.FIRST_HOME / "parent-terminal-audit.json")], p.FIRST_AUDIT_SHA256)
        for replica, arm, package in p.COMPLETED:
            home = package / p.run_id(replica, arm)
            for name in ("registration-final.json", "parent-terminal-audit.json", "lease-release.json"):
                self.assertIn(str(home / name), pins)
        for key in p.REMAINING:
            path = p.run_home(*key) / "registration-final-candidate.json"
            self.assertEqual(pins[str(path)], p.sha(path))
        for name in ("start_remaining_one.py", "remaining_plan.py", "power_guard.py", "watch_progress.py", "producer-home-remap.json"):
            self.assertIn(str(p.HERE / name), pins)

    def test_dependency_inventory_still_matches(self):
        gates = p.read(p.HERE / "parent-gates-proposal.json")
        self.assertEqual(p.sha(gates["dependency_inventory_path"]), gates["dependency_inventory_sha256"])
        inventory = p.read(gates["dependency_inventory_path"])
        self.assertEqual(len(inventory["pins"]), gates["dependency_pins_checked"])
        for path, item in inventory["pins"].items():
            self.assertEqual(p.sha(path), item["sha256"], path)

    def test_import_has_no_side_effects(self):
        before = sorted(str(x) for x in p.HERE.rglob("*") if "tmp" not in x.parts)
        import importlib
        importlib.reload(launcher)
        self.assertEqual(before, sorted(str(x) for x in p.HERE.rglob("*") if "tmp" not in x.parts))

    def test_launch_refuses_without_promoted_files(self):
        with self.assertRaisesRegex(ValueError, "prospective packet"):
            launcher.gate_check(p.HERE, RUNS[0], "0" * 64, "0" * 64)

    def test_launcher_changes_are_only_the_documented_ones(self):
        text = (p.HERE / "start_remaining_one.py").read_text()
        for needle in ("power_guard.check()", "SPENT_NAMES", "binding origin mismatch", "stale authority pinned"):
            self.assertIn(needle, text)
        self.assertEqual(p.sha(p.HERE / "watch_progress.py"), p.sha(p.PARENT_PKG / "watch_progress.py"))
        self.assertIn("start_new_session=True", text)  # observer ownership unchanged


class RemapAndActivation(unittest.TestCase):
    def test_remap_covers_only_three_endpoints_and_leaves_d4_plan_alone(self):
        remap = p.read(p.HERE / "producer-home-remap.json")
        plan_path = Path(remap["d4_policy_plan"])
        self.assertEqual(p.sha(plan_path), remap["d4_policy_plan_sha256"])
        self.assertEqual(sorted(remap["endpoints"]), sorted(RUNS))
        index = {r["run_id"]: r["registration_sha256"] for r in p.read(p.HERE / "registration-index-proposal.json")["runs"]}
        policies = [x for x in p.read(plan_path)["policies"]]
        self.assertEqual(len(policies), 7)  # six endpoints + parent324 stay fixed
        for run_id, entry in remap["endpoints"].items():
            original = next(x for x in policies if x.get("run_id") == run_id)
            self.assertEqual(entry["original"], original)
            self.assertEqual(entry["recovery_registration_candidate_sha256"], index[run_id])
            for key in entry["changed_keys"]:
                self.assertIn(str(p.PARENT_PKG / run_id), original[key])
                self.assertIn(str(p.HERE / run_id), entry["proposed"][key])
                self.assertNotIn(str(p.PARENT_PKG), entry["proposed"][key])
            self.assertEqual({k for k in entry["original"] if k not in entry["changed_keys"]} & {"run_id", "arm", "replica", "id"},
                             {"run_id", "arm", "replica", "id"})
        self.assertIn("not_applied", remap["status"])

    def test_activation_template_records_no_approval_and_scoped_caffeinate(self):
        t = p.read(p.HERE / "activation-template.json")
        self.assertEqual(t["user_approval"], "NOT_GIVEN")
        self.assertIs(t["launch_authority"], False)
        fields = t["authorization_document"]["fields"]
        self.assertEqual(fields["runs"], [dict(run_id=r["run_id"], registration_sha256=r["registration_sha256"])
                         for r in p.read(p.HERE / "registration-index-proposal.json")["runs"]])
        self.assertEqual(fields["retries"], 0)
        self.assertIn("VERBATIM", fields["user_message"])
        self.assertEqual(fields["index_proposal_sha256"], p.sha(p.HERE / "registration-index-proposal.json"))
        for run_id, command in t["launch_command_template"]["runs"].items():
            self.assertEqual(command[:3], ["/usr/bin/caffeinate", "-ims", "/usr/bin/env"])
            self.assertNotIn("-u", command)
            self.assertNotIn("-d", command)
            self.assertFalse(any("pmset" in x for x in command))
            self.assertIn("--run-id", command)
            self.assertEqual(command[command.index("--run-id") + 1], run_id)


class PowerGuard(unittest.TestCase):
    ASSERTIONS = ("Listed by owning process:\n"
                  "   pid 500(caffeinate): [0x1] 00:00:01 PreventUserIdleSystemSleep named: \"caffeinate command-line tool\"\n"
                  "   pid 500(caffeinate): [0x2] 00:00:01 PreventSystemSleep named: \"caffeinate command-line tool\"\n")

    def runner(self, batt="Now drawing from 'AC Power'\n", command="/usr/bin/caffeinate -ims /usr/bin/env X=1 py", assertions=None):
        def run(argv):
            if argv[0].endswith("pmset") and argv[2] == "batt":
                return batt
            if argv[0].endswith("ps"):
                return command + "\n"
            return self.ASSERTIONS if assertions is None else assertions
        return run

    def test_pass(self):
        receipt = power_guard.check(self.runner(), pid=501, ppid=500)
        self.assertTrue(receipt["on_ac"])
        self.assertEqual(receipt["assertions"], ["PreventSystemSleep", "PreventUserIdleSystemSleep"])

    def test_battery_refused(self):
        with self.assertRaisesRegex(ValueError, "AC"):
            power_guard.check(self.runner(batt="Now drawing from 'Battery Power'\n"), pid=501, ppid=500)

    def test_wrong_parent_refused(self):
        for command in ("/bin/zsh -c x", "/usr/bin/caffeinate -u py", "/usr/bin/caffeinate -i py"):
            with self.assertRaisesRegex(ValueError, "exactly"):
                power_guard.check(self.runner(command=command), pid=501, ppid=500)

    def test_missing_or_foreign_assertion_refused(self):
        with self.assertRaisesRegex(ValueError, "not held"):
            power_guard.check(self.runner(assertions="Listed by owning process:\n"), pid=501, ppid=500)
        with self.assertRaisesRegex(ValueError, "not held"):
            power_guard.check(self.runner(), pid=501, ppid=499)


class Fixture:
    """Temporary promoted packet over real immutable evidence and a fake ledger."""
    def __init__(self, key=(2, "opening_priority")):
        TMP_ROOT.mkdir(exist_ok=True)
        self.base = Path(tempfile.mkdtemp(dir=TMP_ROOT))
        self.key, self.rid = key, p.run_id(*key)
        self.home = self.base / self.rid
        self.home.mkdir()
        (self.home / "empty-pycache").mkdir()
        draft = p.read(p.DRAFT_DIR / f"replica-{key[0]}-{key[1]}.json")
        self.state = self.base / "ledger" / "state.json"
        self.state.parent.mkdir()
        self.state.write_text(json.dumps(dict(active_long_campaign=None, active_inference_diagnostic=None,
                                              training_hold=dict(active=False))))
        reg = p.to_candidate(draft, self.home, "ab" * 16, p.LEASE_KIND)
        reg["state_path"] = str(self.state)
        self.candidate = self.home / "registration-final-candidate.json"
        self.candidate.write_bytes(p.dump(reg))
        self.row = dict(run_id=self.rid, replica=key[0], arm=key[1], registration=str(self.home / "registration-final.json"),
                        registration_candidate=str(self.candidate), registration_sha256=p.sha(self.candidate),
                        source_manifest_sha256=p.SOURCE_MANIFEST_SHA256, runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256)
        self.rewrite_proposals()

    def rewrite_proposals(self):
        index = dict(p.read(p.HERE / "registration-index-proposal.json"), runs=[self.row])
        index_path = self.base / "registration-index-proposal.json"
        index_path.write_bytes(p.dump(index))
        self.proposal_index = index
        gates = p.read(p.HERE / "parent-gates-proposal.json")
        pins = {k: v for k, v in gates["pins"].items()
                if Path(k).parent != p.HERE and p.HERE not in Path(k).parents}
        pins.update({k: v for k, v in gates["pins"].items() if Path(k).parent == p.HERE})
        pins.pop(str(p.HERE / "registration-index-proposal.json"), None)
        pins[str(index_path)] = p.sha(index_path)
        pins[str(self.candidate)] = p.sha(self.candidate)
        gates.update(pins=pins, registration_index_proposal_sha256=p.sha(index_path))
        (self.base / "parent-gates-proposal.json").write_bytes(p.dump(gates))

    def build(self, *, gates_mutator=None, auth_mutator=None, index_mutator=None, review_mutator=None, manifest_mutator=None):
        proposal = p.read(self.base / "parent-gates-proposal.json")
        pins = dict(proposal["pins"])
        built = datetime.datetime.fromisoformat(proposal["packet_built_at_utc"])
        auth = dict(schema=p.AUTH_SCHEMA, user_message="fixture-only approval of the three-run recovery plan",
                    at_utc=(built + datetime.timedelta(hours=1)).isoformat(), retries=0, max_registered_training_attempts=3,
                    source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
                    index_proposal_sha256=proposal["registration_index_proposal_sha256"],
                    failure_audit_sha256=p.FAILURE_AUDIT_SHA256,
                    runs=[dict(run_id=self.rid, registration_sha256=self.row["registration_sha256"])])
        if auth_mutator:
            auth_mutator(auth)
        auth_path = self.base / "fresh-user-authorization.json"
        auth_path.write_bytes(p.dump(auth))
        pins[str(auth_path)] = p.sha(auth_path)
        manifest = dict(files={name: p.sha(self.base / name) for name in
                               ("registration-index-proposal.json", "parent-gates-proposal.json")})
        if manifest_mutator:
            manifest_mutator(manifest)
        manifest_path = self.base / "package-manifest.json"
        manifest_path.write_bytes(p.dump(manifest))
        review = dict(verdict="accepted", package_manifest_sha256=p.sha(manifest_path))
        if review_mutator:
            review_mutator(review)
        review_path = self.base / "review.json"
        review_path.write_bytes(p.dump(review))
        pins[str(manifest_path)] = p.sha(manifest_path)
        pins[str(review_path)] = p.sha(review_path)
        gates = dict(proposal, status=p.GATES_APPROVED_STATUS, pins=pins, authorization_path=str(auth_path),
                     authorization_sha256=p.sha(auth_path), proposal_sha256=p.sha(self.base / "parent-gates-proposal.json"),
                     independent_review=dict(path=str(review_path), sha256=p.sha(review_path),
                                             package_manifest_sha256=p.sha(manifest_path)))
        index = dict(self.proposal_index, status=p.INDEX_PROMOTED_STATUS)
        if index_mutator:
            index_mutator(index)
        (self.base / "registration-index.json").write_bytes(p.dump(index))
        gates["registration_index_sha256"] = p.sha(self.base / "registration-index.json")
        if gates_mutator:
            gates_mutator(gates)
        (self.base / "parent-gates.json").write_bytes(p.dump(gates))
        return p.sha(self.base / "registration-index.json"), p.sha(self.base / "parent-gates.json")

    def check(self, **kwargs):
        index_sha, gates_sha = self.build(**kwargs)
        return launcher.gate_check(self.base, self.rid, index_sha, gates_sha, state_path=self.state)


class LauncherGates(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        shutil.rmtree(self.fx.base, ignore_errors=True)

    def test_positive_fixture_passes_and_is_read_only(self):
        before = sorted(x.name for x in self.fx.home.iterdir())
        row, reg, gates, inventory = self.fx.check()
        self.assertEqual(row["run_id"], self.fx.rid)
        self.assertEqual(sorted(x.name for x in self.fx.home.iterdir()), before)
        self.assertFalse((self.fx.home / "registration-final.json").exists())

    def test_proposal_status_gates_refused(self):
        with self.assertRaisesRegex(ValueError, "only a proposal"):
            self.fx.check(gates_mutator=lambda g: g.update(status=p.GATES_PROPOSAL_STATUS))

    def test_unpromoted_index_refused(self):
        with self.assertRaisesRegex(ValueError, "promoted proposal rows"):
            self.fx.check(index_mutator=lambda i: i.update(status=p.INDEX_PROPOSAL_STATUS))

    def test_completed_and_failed_old_runs_cannot_be_launched(self):
        index_sha, gates_sha = self.fx.build()
        for run_id in (p.FIRST_RUN_ID, p.run_id(2, "uniform"), p.run_id(1, "opening_priority")):
            with self.assertRaisesRegex(ValueError, "exact remaining index"):
                launcher.gate_check(self.fx.base, run_id, index_sha, gates_sha, state_path=self.fx.state)

    def test_authorization_must_name_exact_run_registration_and_zero_retries(self):
        for mutator in (lambda a: a.update(runs=[]), lambda a: a["runs"][0].update(registration_sha256="0" * 64),
                        lambda a: a.update(retries=1), lambda a: a.update(user_message=" "),
                        lambda a: a.update(failure_audit_sha256="0" * 64), lambda a: a.update(index_proposal_sha256="0" * 64)):
            with self.assertRaisesRegex(ValueError, "does not name this exact run"):
                self.fx.check(auth_mutator=mutator)

    def test_consumed_message_and_stale_timestamp_refused(self):
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a.update(user_message=p.CONSUMED_USER_MESSAGES[0]))
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a.update(at_utc="2026-10-27T00:00:00+00:00"))

    def test_missing_reviewed_pin_refused(self):
        victim = str(p.R3 / "source-manifest.json")
        with self.assertRaisesRegex(ValueError, "every reviewed proposal pin"):
            self.fx.check(gates_mutator=lambda g: g["pins"].pop(victim))

    def test_required_recovery_pins_enforced(self):
        for victim, message in ((str(p.FAILURE / "audit.json"), "failure audit"),
                                (str(p.FAILURE / "lease-release.json"), "failure audit"),
                                (str(p.CHECKPOINT), "checkpoint and receipt")):
            fx = Fixture()
            try:
                proposal = p.read(fx.base / "parent-gates-proposal.json")
                proposal["pins"].pop(victim)  # absent from the reviewed proposal too, so only the explicit check can catch it
                (fx.base / "parent-gates-proposal.json").write_bytes(p.dump(proposal))
                with self.assertRaisesRegex(ValueError, message):
                    fx.check(gates_mutator=lambda g: g["pins"].pop(victim, None))
            finally:
                shutil.rmtree(fx.base, ignore_errors=True)

    def test_stale_authority_pin_refused(self):
        stale = p.PARENT_PKG / "registration-index.json"
        self.assertTrue(stale.exists())
        with self.assertRaisesRegex(ValueError, "stale authority"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update({str(stale): p.sha(stale)}))

    def test_index_proposal_binding(self):
        with self.assertRaisesRegex(ValueError, "exact index proposal"):
            self.fx.check(gates_mutator=lambda g: g.update(registration_index_proposal_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "promoted index"):
            self.fx.check(gates_mutator=lambda g: g.update(registration_index_sha256="0" * 64))

    def test_independent_review_and_manifest_binding(self):
        with self.assertRaisesRegex(ValueError, "independent review"):
            self.fx.check(gates_mutator=lambda g: g.pop("independent_review"))
        with self.assertRaisesRegex(ValueError, "independent review"):
            self.fx.check(gates_mutator=lambda g: g["independent_review"].update(package_manifest_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "differs from reviewed manifest"):
            self.fx.check(manifest_mutator=lambda m: m["files"].update({"parent-gates-proposal.json": "0" * 64}))

    def test_pin_drift_refused(self):
        extra = {str(p.R3 / "README.md"): "0" * 64}
        with self.assertRaisesRegex(ValueError, "pin drift"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update(extra))

    def test_mutable_ledger_may_not_be_pinned(self):
        pin = {str(self.fx.state): p.sha(self.fx.state)}
        with self.assertRaisesRegex(ValueError, "mutable ledger"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update(pin))

    def test_spent_paths_refused(self):
        for name in ("attempt.claimed", "launch.claimed", "worker-output", "progress-reports.jsonl", "progress-alert.json",
                     "cancel", "dispatch", "observer.log", "execution-exit.json"):
            path = self.fx.home / name
            path.mkdir() if name in ("worker-output", "dispatch") else path.write_text("x")
            try:
                with self.assertRaisesRegex(ValueError, "already spent"):
                    self.fx.check()
            finally:
                shutil.rmtree(path) if path.is_dir() else path.unlink()

    def test_shared_pending_state_refused(self):
        pending = self.fx.state.with_name(launcher.PENDING_STATE)
        pending.write_text("{}")
        with self.assertRaisesRegex(ValueError, "pending path"):
            self.fx.check()

    def test_active_campaign_or_hold_refused(self):
        self.fx.state.write_text(json.dumps(dict(active_long_campaign={"x": 1}, active_inference_diagnostic=None,
                                                 training_hold=dict(active=False))))
        with self.assertRaisesRegex(ValueError, "conflicting campaign"):
            self.fx.check()
        self.fx.state.write_text(json.dumps(dict(active_long_campaign=None, active_inference_diagnostic=None,
                                                 training_hold=dict(active=True))))
        with self.assertRaisesRegex(ValueError, "training hold"):
            self.fx.check()

    def test_registration_final_must_equal_candidate_and_materialize_is_exclusive(self):
        index_sha, gates_sha = self.fx.build()
        row, *_ = launcher.gate_check(self.fx.base, self.fx.rid, index_sha, gates_sha, state_path=self.fx.state)
        launcher.materialize(row)
        final = self.fx.home / "registration-final.json"
        self.assertEqual(final.read_bytes(), self.fx.candidate.read_bytes())
        launcher.materialize(row)  # equal bytes: idempotent
        final.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "differs"):
            launcher.materialize(row)

    def test_registration_paths_must_stay_in_run_directory(self):
        reg = p.read(self.fx.candidate)
        reg["output"] = str(self.fx.base / "elsewhere")
        self.fx.candidate.write_bytes(p.dump(reg))
        self.fx.row["registration_sha256"] = p.sha(self.fx.candidate)
        self.fx.rewrite_proposals()
        with self.assertRaisesRegex(ValueError, "escapes its run directory"):
            self.fx.check()


class Monitor(unittest.TestCase):
    ROW = dict(total_updates=60, work_limit_seconds=3780, projected_work_deadline_miss=False, elapsed_seconds=10)

    def test_assess(self):
        self.assertIsNone(monitor.assess(None, 5, 3780, 60))
        self.assertEqual(monitor.assess(None, 130, 3780, 60), "no_progress_for_120_seconds")
        self.assertIsNone(monitor.assess(self.ROW, 20, 3780, 60))
        self.assertEqual(monitor.assess(dict(self.ROW, total_updates=24), 20, 3780, 60), "progress_registration_mismatch")
        self.assertEqual(monitor.assess(dict(self.ROW, projected_work_deadline_miss=True), 20, 3780, 60),
                         "projected_work_deadline_miss")
        self.assertEqual(monitor.assess(self.ROW, 200, 3780, 60), "progress_stale_for_120_seconds")

    def test_last_complete_row_ignores_torn_tail(self):
        TMP_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as directory:
            path = Path(directory) / "reports.jsonl"
            path.write_bytes(b'{"a": 1}\n{"a": 2}\n{"a": 3')
            self.assertEqual(monitor.last_complete_row(path), {"a": 2})
            self.assertIsNone(monitor.last_complete_row(Path(directory) / "missing"))


if __name__ == "__main__":
    unittest.main()
