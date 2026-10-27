"""Focused actual-schema controls; no checkpoint or run-output writes."""
import copy, importlib.util, os, subprocess, sys, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("candidate_auditor_r2",HERE/"audit_candidates.py")
auditor=importlib.util.module_from_spec(spec); sys.modules[spec.name]=auditor; spec.loader.exec_module(auditor)
r=auditor.bind_frozen_runner()

class CandidateGateControls(unittest.TestCase):
    def setUp(self):
        self.config={"ppo":{"learning_rate":0.0001}}
        self.reg={"run_seed":3791628417,"config_sha256":"config","native":{"sha256":"native"},"runtime_sha256":"runtime","_config":copy.deepcopy(self.config)}
        self.parent={"identity":{"architecture":{"layers":[128,64]}},"cumulative_counters":{"updates":228,"optimizer_steps":10,"environment_decisions":20,"raw_frames":30},"abandoned_current_episodes":[{"slot":0}]}
        self.counters={"updates":12,"optimizer_steps":24,"environment_decisions":196608,"raw_frames":9000}
        self.state={"phase":"D2","phase_update":192,"local_update":12,"registration_sha256":auditor.REG_SHA,"config_sha256":"config","native_sha256":"native","runtime_sha256":"runtime","policy_sha256":r.POLICY_SHA,"parent_sha256":auditor.PARENT_SHA,"parent_checkpoint_sha256":auditor.PARENT_SHA,"parent_registration_sha256":r.PARENT_REGISTRATION_SHA,"parent_run_id":"D2-gradient-alignment-20261025-r2","run_seed":3791628417,"identity":{"version":"teacher_identity_v3","run_id":r.RUN_ID,"phase":"D2","phase_update_start":180,"phase_update_end":252,"run_seed":3791628417,"config":copy.deepcopy(self.config),"parent_checkpoint_sha256":auditor.PARENT_SHA,"policy_sha256":r.POLICY_SHA,"registration_sha256":auditor.REG_SHA,"architecture":{"layers":[128,64]}},"counters":copy.deepcopy(self.counters),"inherited_counters":copy.deepcopy(self.parent["cumulative_counters"]),"parent_abandoned_current_episodes":copy.deepcopy(self.parent["abandoned_current_episodes"]),"cumulative_counters":{"updates":240,"optimizer_steps":34,"environment_decisions":196628,"raw_frames":9030}}
        self.metric={"local_update":12,"counters":copy.deepcopy(self.counters)}
        self.resume={"next_episode_indices":[2]*64,"abandoned_current_episodes":[{"slot":i,"seed":{"slot":i,"episode":1},"gameplay_frames":i} for i in range(64)]}
    def accepted(self,state=None,metric=None):
        auditor.validate_snapshot_binding(state or self.state,self.reg,self.parent,r,192,metric or self.metric)
    def test_actual_schema_binding_accepts(self): self.accepted()
    def test_five_corrupt_midcandidate_controls_reject(self):
        mutations=(
            ("identity.config",lambda s,m:s["identity"].update(config={"ppo":{"learning_rate":0.2}})),
            ("parent registration",lambda s,m:s.update(parent_registration_sha256="bad")),
            ("phase update",lambda s,m:s.update(phase_update=204)),
            ("metric counters",lambda s,m:m["counters"].update(raw_frames=9001)),
            ("cumulative base",lambda s,m:s["cumulative_counters"].update(updates=192)),
        )
        for name,mutate in mutations:
            state=copy.deepcopy(self.state); metric=copy.deepcopy(self.metric); mutate(state,metric)
            with self.subTest(name=name),self.assertRaises((ValueError,AssertionError)): self.accepted(state,metric)
    def test_resume_lineage_rejects_corruption_and_allows_duplicate_episode_values(self):
        auditor.validate_resume_snapshot(self.resume)
        bad=copy.deepcopy(self.resume); bad["abandoned_current_episodes"][17]["seed"]["episode"]+=1
        with self.assertRaises(ValueError): auditor.validate_resume_snapshot(bad)
        bad=copy.deepcopy(self.resume); bad["abandoned_current_episodes"].pop()
        with self.assertRaises(ValueError): auditor.validate_resume_snapshot(bad)
        bad=copy.deepcopy(self.resume); bad["next_episode_indices"]=tuple(bad["next_episode_indices"])
        with self.assertRaises(ValueError): auditor.validate_resume_snapshot(bad)
    def test_ranking_positive_tie_and_no_improvement_controls(self):
        self.assertEqual(auditor.choose_best({180:{"mean_alive_frames":1854.46875},204:{"mean_alive_frames":1921.171875}},1854.46875),204)
        self.assertIsNone(auditor.choose_best({180:{"mean_alive_frames":1854.46875},204:{"mean_alive_frames":1854.46875}},1854.46875))
        self.assertIsNone(auditor.choose_best({180:{"mean_alive_frames":1800.0}},1854.46875))
    def test_standalone_launcher_runner_import_is_pinned(self):
        python=auditor.ROOT/"python/.venv/bin/python"
        cache=auditor.ROOT/"learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/empty-pycache-prefix"
        code=f"import sys; p={str(auditor.SRC)!r}; sys.path.insert(0,p); import execute_once; assert sys.modules['runner'].__file__ == p + '/runner.py'; print(sys.modules['runner'].__file__)"
        env=dict(os.environ,PYTHONPYCACHEPREFIX=str(cache))
        got=subprocess.check_output([str(python),"-B","-c",code],cwd=auditor.ROOT,env=env,text=True).strip()
        self.assertEqual(Path(got).resolve(),(auditor.SRC/"runner.py").resolve())
    def test_refuses_to_overwrite_existing_audit_output(self):
        python=auditor.ROOT/"python/.venv/bin/python"
        cache=auditor.ROOT/"learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/empty-pycache-prefix"
        output=HERE/"provisional-frozen.json"; before=auditor.digest(output)
        env=dict(os.environ,PYTHONPYCACHEPREFIX=str(cache))
        run=subprocess.run([str(python),"-B",str(HERE/"audit_candidates.py"),"--provisional","--output",str(output)],
                           cwd=auditor.ROOT,env=env,text=True,capture_output=True)
        self.assertNotEqual(run.returncode,0)
        self.assertIn("Refusing to overwrite audit output",run.stderr)
        self.assertEqual(auditor.digest(output),before)

if __name__=="__main__": unittest.main(verbosity=2)
