"""Stdlib CPU/fake checks for the remaining seed-priority r3 bindings.

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

    def test_remaining_set_is_exactly_five_and_excludes_first(self):
        self.assertEqual(len(RUNS), 5)
        self.assertNotIn(p.FIRST_RUN_ID, RUNS)
        self.assertEqual(set(p.REMAINING) | {(1, "uniform")}, set(p.DRAFT_SHA256))


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
        self.assertEqual(len(set(tokens + [p.FIRST_OWNER_TOKEN])), 6)

    def test_candidates_reference_r3_only(self):
        for key in p.REMAINING:
            text = (p.run_home(*key) / "registration-final-candidate.json").read_text()
            self.assertNotIn("experiment-luna-20261027-r2", text)
            self.assertNotIn("experiment-luna-20261027-r1", text)
            self.assertIn("experiment-luna-20261027-r3", text)

    def test_pool_disjoint_from_exclusions_and_d4_d5_unopened(self):
        reg = candidate(1, "opening_priority")
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
        pairs = {1: (p.read(p.FIRST_HOME / "registration-final.json"), candidate(1, "opening_priority")),
                 2: (candidate(2, "uniform"), candidate(2, "opening_priority")),
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
        self.assertEqual(gates["status"], p.GATES_PROPOSAL_STATUS)
        self.assertIs(gates["launch_authority"], False)
        self.assertTrue(gates["authorization"].startswith("NOT AUTHORIZED"))
        self.assertEqual([r["run_id"] for r in index["runs"]], RUNS)
        for row in index["runs"]:
            self.assertEqual(p.sha(row["registration_candidate"]), row["registration_sha256"])
            self.assertFalse(Path(row["registration"]).exists())
        self.assertEqual(gates["registration_index_proposal_sha256"], p.sha(p.HERE / "registration-index-proposal.json"))

    def test_gate_pins_hold_and_exclude_mutable_ledger_and_consumed_authority(self):
        gates = p.read(p.HERE / "parent-gates-proposal.json")
        for path, digest in gates["pins"].items():
            self.assertEqual(p.sha(path), digest, path)
        names = {Path(path).name for path in gates["pins"]}
        self.assertNotIn("state.json", names)
        self.assertIn("seed-history-ledger-snapshot.json", names)
        self.assertNotIn(str(p.PRIOR / "fresh-user-authorization.json"), gates["pins"])
        self.assertNotIn(str(p.PRIOR / "start_one.py"), gates["pins"])
        self.assertFalse(any("experiment-luna-20261027-r2" in path for path in gates["pins"]))
        self.assertEqual(gates["pins"][str(p.R3 / "source-manifest.json")], p.SOURCE_MANIFEST_SHA256)
        self.assertEqual(gates["pins"][str(p.R3 / "runtime-manifest.json")], p.RUNTIME_MANIFEST_SHA256)
        self.assertEqual(gates["pins"][str(p.FIRST_HOME / "parent-terminal-audit.json")], p.FIRST_AUDIT_SHA256)
        self.assertEqual(gates["pins"][str(p.FIRST_HOME / "registration-final.json")], p.FIRST_REGISTRATION_SHA256)
        for key in p.REMAINING:
            path = p.run_home(*key) / "registration-final-candidate.json"
            self.assertEqual(gates["pins"][str(path)], p.sha(path))

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


class Fixture:
    """Temporary promoted packet over real immutable evidence and a fake ledger."""
    def __init__(self, key=(1, "opening_priority")):
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
        for name in ("registration-index-proposal.json", "parent-gates-proposal.json"):
            shutil.copy(p.HERE / name, self.base / name)
        self.proposal_index = p.read(self.base / "registration-index-proposal.json")
        row = dict(run_id=self.rid, replica=key[0], arm=key[1], registration=str(self.home / "registration-final.json"),
                   registration_candidate=str(self.candidate), registration_sha256=p.sha(self.candidate),
                   source_manifest_sha256=p.SOURCE_MANIFEST_SHA256, runtime_manifest_sha256=p.RUNTIME_MANIFEST_SHA256)
        self.proposal_index["runs"] = [row]
        (self.base / "registration-index-proposal.json").write_bytes(p.dump(self.proposal_index))
        self.row = row

    def build(self, *, gates_mutator=None, auth_mutator=None, index_mutator=None):
        proposal = p.read(self.base / "parent-gates-proposal.json")
        pins = dict(proposal["pins"])
        pins[str(self.candidate)] = p.sha(self.candidate)
        auth = dict(schema=p.AUTH_SCHEMA, user_message="fixture-only authorization text", retries=0,
                    source_manifest_sha256=p.SOURCE_MANIFEST_SHA256,
                    runs=[dict(run_id=self.rid, registration_sha256=self.row["registration_sha256"])])
        if auth_mutator:
            auth_mutator(auth)
        auth_path = self.base / "fresh-user-authorization.json"
        auth_path.write_bytes(p.dump(auth))
        pins[str(auth_path)] = p.sha(auth_path)
        gates = dict(proposal, status=p.GATES_APPROVED_STATUS, pins=pins, authorization_path=str(auth_path),
                     authorization_sha256=p.sha(auth_path), proposal_sha256=p.sha(self.base / "parent-gates-proposal.json"))
        if gates_mutator:
            gates_mutator(gates)
        index = dict(self.proposal_index, status=p.INDEX_PROMOTED_STATUS)
        if index_mutator:
            index_mutator(index)
        (self.base / "parent-gates.json").write_bytes(p.dump(gates))
        (self.base / "registration-index.json").write_bytes(p.dump(index))
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

    def test_first_run_cannot_be_relaunched(self):
        index_sha, gates_sha = self.fx.build()
        with self.assertRaisesRegex(ValueError, "exact remaining index"):
            launcher.gate_check(self.fx.base, p.FIRST_RUN_ID, index_sha, gates_sha, state_path=self.fx.state)

    def test_authorization_must_name_exact_run_registration_and_zero_retries(self):
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a.update(runs=[]))
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a["runs"][0].update(registration_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a.update(retries=1))
        with self.assertRaisesRegex(ValueError, "does not name this exact run"):
            self.fx.check(auth_mutator=lambda a: a.update(user_message=" "))

    def test_missing_reviewed_pin_refused(self):
        victim = str(p.R3 / "source-manifest.json")
        with self.assertRaisesRegex(ValueError, "every reviewed proposal pin"):
            self.fx.check(gates_mutator=lambda g: g["pins"].pop(victim))

    def test_pin_drift_refused(self):
        extra = {str(p.R3 / "README.md"): "0" * 64}
        with self.assertRaisesRegex(ValueError, "pin drift"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update(extra))
        victim = str(p.R3 / "source-manifest.json")
        with self.assertRaisesRegex(ValueError, "every reviewed proposal pin"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update({victim: "0" * 64}))

    def test_mutable_ledger_may_not_be_pinned(self):
        pin = {str(self.fx.state): p.sha(self.fx.state)}
        with self.assertRaisesRegex(ValueError, "mutable ledger"):
            self.fx.check(gates_mutator=lambda g: g["pins"].update(pin))

    def test_spent_paths_refused(self):
        (self.fx.home / "attempt.claimed").write_text("x")
        with self.assertRaisesRegex(ValueError, "already spent"):
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
        self.fx.proposal_index["runs"] = [self.fx.row]
        (self.fx.base / "registration-index-proposal.json").write_bytes(p.dump(self.fx.proposal_index))
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
