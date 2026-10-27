from __future__ import annotations
import ast, importlib.util, json, os, sys, tempfile, types, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'execute_once.py'

class LauncherContract(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp(dir=HERE))
        self.runner=types.ModuleType('runner')
        self.runner.LIMITS={'work_seconds':1790,'total_seconds':1800}
        self.runner.PHASE_START=300; self.runner.PHASE_END=360; self.runner.NEW_UPDATES=60
        self.runner.EVALUATION_UPDATES=(300,312,324,336,348,360)
        self.runner.assert_saved_optimizer_lr=lambda state,lr: None
        self.runner.Cancelled=type('Cancelled',(Exception,),{})
        self.runner.read=lambda p: json.loads(Path(p).read_text())
        self.runner.need=lambda ok,msg: (_ for _ in ()).throw(ValueError(msg)) if not ok else None
        self.runner.load_registration=lambda p,s:(json.loads(Path(p).read_text()),None)
        self.runner.save=lambda p,v: Path(p).write_text(json.dumps(v))
        self.runner.check_lease=lambda reg:None
        self.runner.sha=lambda p:'fixture'
        self.runner.check_import_cache=lambda reg:None
        self.schema=types.ModuleType('registration_schema')
        self.schema.validate_identity=lambda reg: self.runner.need(reg.get('identity_ok') is True,'invalid identity')
        sys.modules['runner']=self.runner; sys.modules['registration_schema']=self.schema
        spec=importlib.util.spec_from_file_location('launcher_fixture',SOURCE)
        self.mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
    def tearDown(self):
        sys.modules.pop('runner',None); sys.modules.pop('registration_schema',None)
        import shutil; shutil.rmtree(self.tmp,ignore_errors=True)
    def test_invalid_registration_fails_before_mutation(self):
        out=self.tmp/'never-created'; reg=self.tmp/'bad.json'
        reg.write_text(json.dumps({'output':str(out),'identity_ok':False}))
        with self.assertRaises(ValueError): self.mod.execute(reg,'0'*64)
        self.assertFalse(out.exists()); self.assertFalse((out/'launch-marker.json').exists())
    def test_valid_registration_reaches_real_popen_after_pins(self):
        out=self.tmp/'out'; reg=self.tmp/'good.json'
        reg.write_text(json.dumps({'output':str(out),'identity_ok':True,'launcher_path':str(SOURCE),
          'interpreter':'python','runner_path':'runner.py','registration_sha256':'0'*64,
          'root':str(self.tmp),'runtime_root':str(self.tmp),'import_policy':{'pycache_prefix':str(self.tmp/'cache')}}))
        events=[]
        def loaded(path,digest): events.append('pins-loaded'); return json.loads(Path(path).read_text()),None
        self.runner.load_registration=loaded
        def popen(*a,**kw):
            events.append('popen')
            raise RuntimeError('controlled stop at subprocess boundary')
        result=self.mod.execute(reg,'0'*64,popen=popen)
        self.assertEqual(result,1); self.assertEqual(events,['pins-loaded','popen'])
        self.assertTrue((out/'launch-marker.json').exists())
    def test_checkpoint_counter_and_boundary_contract(self):
        metrics=[{'phase_update':312,'counters':{'updates':12,'optimizer_steps':768,'environment_decisions':196608,'raw_frames':1234}}]
        self.assertEqual(self.mod.expected_checkpoint_counters(300,metrics),
          {'updates':0,'optimizer_steps':0,'environment_decisions':0,'raw_frames':0})
        self.assertEqual(self.mod.expected_checkpoint_counters(312,metrics),metrics[0]['counters'])
        state={'phase_update':312,'local_update':12,'update_progress':{'complete':True,'in_update':False,'completed_updates':12},'counters':metrics[0]['counters']}
        self.mod.validate_terminal_candidate_binding(state,312,metrics[0]['counters'])
    def test_production_execution_path_and_no_lr_transition(self):
        tree=ast.parse(SOURCE.read_text())
        execute=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
        calls=[n.func.attr for n in ast.walk(execute) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertTrue(any(arg.arg=='popen' for arg in execute.args.kwonlyargs))
        self.assertTrue(any(isinstance(n,ast.Attribute) and n.attr=='Popen' for n in ast.walk(tree)))
        self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='popen' for n in ast.walk(execute)))
        self.assertIn('load_registration',calls)
        self.assertIn('check_lease',calls)
        text=SOURCE.read_text()
        self.assertNotIn('lr-transition.json',text)
        self.assertIn('stop_owned(process)',text)

if __name__=='__main__': unittest.main(verbosity=2)
