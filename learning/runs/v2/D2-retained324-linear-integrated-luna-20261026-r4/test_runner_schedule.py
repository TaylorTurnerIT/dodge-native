"""CPU-only tests of actual runner schedule functions with synthetic optimizer state."""
import copy, hashlib, math, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import parent_adapter, registration_schema, runner
assert Path(parent_adapter.__file__).resolve()==ROOT/'parent_adapter.py'
assert Path(registration_schema.__file__).resolve()==ROOT/'registration_schema.py'
class Optimizer:
    def __init__(self): self.param_groups=[{'lr':3e-5},{'lr':3e-5}]
    def state_dict(self): return {'param_groups':[{'lr':g['lr']} for g in self.param_groups]}
class ScheduleTests(unittest.TestCase):
    def test_initialize_stage_commit_saved_lr_full_horizon(self):
        opt=Optimizer(); state=runner.initialize_or_restore_schedule(opt,372)
        self.assertEqual(runner.validate_saved_schedule_lr({'optimizer':opt.state_dict(),'lr_schedule':state},372),3e-5)
        for local in range(60):
            actual=372+local; lr,staged=runner.stage_schedule_update(opt,state,372,local,actual)
            expected=3e-5-2e-5*local/59 if local<59 else 1e-5
            self.assertAlmostEqual(lr,expected,places=15)
            self.assertEqual([g['lr'] for g in opt.param_groups],[lr,lr])
            state=runner.commit_schedule_after_success(state,staged,actual,372,local,True)
            metric=runner.schedule_metric_fields(opt,state,373+local)
            self.assertEqual(metric['optimizer_group_lrs'],[lr,lr])
            if local==11: self.assertEqual(runner.validate_saved_schedule_lr({'optimizer':opt.state_dict(),'lr_schedule':state},384),lr)
        self.assertEqual(state['completed_schedule_updates'],60)
        self.assertEqual(runner.validate_saved_schedule_lr({'optimizer':opt.state_dict(),'lr_schedule':state},432),1e-5)
    def test_missing_or_mismatched_resume_and_failed_commit(self):
        opt=Optimizer(); state=runner.initialize_or_restore_schedule(opt,372)
        for args in ((opt,371),(opt,384,None,True)):
            with self.assertRaises(ValueError): runner.initialize_or_restore_schedule(*args)
        with self.assertRaises(ValueError): runner.validate_future_scheduled_resume(dict(state,completed_schedule_updates=1),372,opt)
        _,staged=runner.stage_schedule_update(opt,state,372,0,372)
        with self.assertRaisesRegex(ValueError,'Cannot commit schedule'):
            runner.commit_schedule_after_success(state,staged,372,372,0,False)
        self.assertEqual(state['completed_schedule_updates'],0)
    def test_actual_helper_source_and_origin(self):
        self.assertEqual(hashlib.sha256((ROOT/'lr_schedule.py').read_bytes()).hexdigest(),runner.LR_SCHEDULE_SHA256)
        self.assertEqual(Path(runner.lr_schedule.__file__).resolve(),ROOT/'lr_schedule.py')
        runner.lr_schedule.verify_frozen_manifest(ROOT)
if __name__=='__main__': unittest.main()
