"""CPU-only metadata negative controls; no checkpoint bytes written."""
import copy, importlib.util, sys, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("candidate_auditor",HERE/"audit_candidates.py")
auditor=importlib.util.module_from_spec(spec); sys.modules[spec.name]=auditor; spec.loader.exec_module(auditor)
SRC=auditor.SRC
r=auditor.load_module("frozen_runner_for_controls",SRC/"runner.py")

class CandidateGateControls(unittest.TestCase):
    def setUp(self):
        self.reg={"run_seed":3791628417,"config_sha256":"config","native":{"sha256":"native"},"runtime_sha256":"runtime"}
        self.parent={"identity":{"architecture":{"layers":[128,64]}},"cumulative_counters":{"updates":228,"optimizer_steps":10,"environment_decisions":20,"raw_frames":30},"abandoned_current_episodes":[{"slot":0}]}
        self.counters={"updates":12,"optimizer_steps":24,"environment_decisions":196608,"raw_frames":9000}
        self.state={"phase":"D2","phase_update":192,"local_update":12,"registration_sha256":auditor.REG_SHA,"config_sha256":"config","native_sha256":"native","runtime_sha256":"runtime","policy_sha256":r.POLICY_SHA,"parent_sha256":auditor.PARENT_SHA,"parent_checkpoint_sha256":auditor.PARENT_SHA,"parent_registration_sha256":r.PARENT_REGISTRATION_SHA,"parent_run_id":"D2-gradient-alignment-20261025-r2","run_seed":3791628417,"identity":{"run_id":r.RUN_ID,"run_seed":3791628417,"registration_sha256":auditor.REG_SHA,"phase":"D2","config_sha256":"config","architecture":{"layers":[128,64]}},"counters":copy.deepcopy(self.counters),"inherited_counters":copy.deepcopy(self.parent["cumulative_counters"]),"parent_abandoned_current_episodes":copy.deepcopy(self.parent["abandoned_current_episodes"]),"cumulative_counters":{"updates":240,"optimizer_steps":34,"environment_decisions":196628,"raw_frames":9030}}
        self.metric={"local_update":12,"counters":copy.deepcopy(self.counters)}
        self.resume={"next_episode_indices":[2]*64,"abandoned_current_episodes":[{"slot":i,"seed":{"slot":i,"episode":1},"gameplay_frames":i} for i in range(64)]}
    def accepted(self,state=None):
        auditor.validate_snapshot_binding(state or self.state,self.reg,self.parent,r,192,self.metric)
    def test_phase_and_local_mutations_rejected(self):
        for key,value in (("phase_update",204),("local_update",13)):
            bad=copy.deepcopy(self.state); bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.accepted(bad)
    def test_identity_registration_and_parent_mutations_rejected(self):
        for key,value in (("registration_sha256","wrong"),("parent_sha256","wrong"),("parent_checkpoint_sha256","wrong"),("parent_registration_sha256","wrong")):
            bad=copy.deepcopy(self.state); bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.accepted(bad)
        bad=copy.deepcopy(self.state); bad["identity"]["run_seed"]+=1
        with self.assertRaises(ValueError): self.accepted(bad)
    def test_cumulative_base_mutation_rejected(self):
        bad=copy.deepcopy(self.state); bad["cumulative_counters"]["updates"]-=48
        with self.assertRaises(ValueError): self.accepted(bad)
    def test_resume_corruption_rejected_but_duplicate_episode_values_across_slots_valid(self):
        auditor.validate_resume_snapshot(self.resume)
        bad=copy.deepcopy(self.resume); bad["abandoned_current_episodes"][17]["seed"]["episode"]+=1
        with self.assertRaises(ValueError): auditor.validate_resume_snapshot(bad)
        bad=copy.deepcopy(self.resume); bad["abandoned_current_episodes"].pop()
        with self.assertRaises(ValueError): auditor.validate_resume_snapshot(bad)
    def test_metric_counter_mismatch_rejected(self):
        bad=copy.deepcopy(self.state); bad["counters"]["raw_frames"]+=1
        with self.assertRaises(ValueError): self.accepted(bad)

if __name__=="__main__": unittest.main(verbosity=2)
