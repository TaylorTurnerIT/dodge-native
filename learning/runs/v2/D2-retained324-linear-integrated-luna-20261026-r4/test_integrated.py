"""CPU-only integrated contract tests; never loads checkpoint binaries or launches training."""
import copy, hashlib, json, sys, unittest, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import parent_adapter, registration_schema, runner, execute_once, build_registration

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class IntegratedTests(unittest.TestCase):
    def build(self):
        p=ROOT
        return build_registration.build_registration(p/'runner-manifest.json',sha(p/'runner-manifest.json'),p/'helper-manifest.json',sha(p/'helper-manifest.json'),p/'launcher-manifest.json',sha(p/'launcher-manifest.json'))
    def test_actual_modules_and_json_registration(self):
        self.assertEqual(Path(parent_adapter.__file__).resolve(),ROOT/'parent_adapter.py')
        self.assertEqual(Path(registration_schema.__file__).resolve(),ROOT/'registration_schema.py')
        reg=self.build(); registration_schema.validate_identity(reg); runner.validate_registration(reg)
        latest=json.loads(Path(reg['resource_cost_anchor']['path']).read_text())
        producing=json.loads(Path(reg['parent']['completed_cost_receipt_path']).read_text())
        self.assertEqual(latest['wall_accounting']['completed_campaign_resource_cost_after_seconds'],10824.835578584221)
        self.assertEqual(producing['wall_accounting']['completed_campaign_resource_cost_after_seconds'],9758.365427209174)
        self.assertEqual(reg['latest_resource_cost_anchor']['sha256'],parent_adapter.LATEST_COST_RECEIPT_SHA256)
    def test_actual_parent_json_runtime_gate_with_synthetic_state(self):
        selected=json.loads(build_registration.SELECTED_RECEIPT_PATH.read_text())
        producing=json.loads(build_registration.PRODUCING_COST_PATH.read_text())
        latest=json.loads(build_registration.LATEST_COST_PATH.read_text())
        metadata=json.loads(Path(selected['checkpoint_path']+'.json').read_text())
        state={k:selected.get(v) for k,v in {'counters':'candidate_counters','cumulative_counters':'candidate_cumulative_counters','inherited_counters':'inherited_counters','next_episode_indices':'next_episode_indices','identity_sha256':'identity_sha256','config_sha256':'config_sha256','runtime_sha256':'runtime_sha256','native_sha256':'native_sha256','policy_sha256':'policy_sha256','registration_sha256':'registration_sha256'}.items()}
        state.update(phase='D2',phase_update=324,local_update=24,tag='candidate',training_eligible=False,promoted=False,eligibility_status='provisional_pending_parent_terminal_receipt',update_progress={'complete':True,'in_update':False,'completed_updates':24},parent_checkpoint_sha256=parent_adapter.PARENT_OF_RUN_SHA256,cumulative_selected_checkpoint_trajectory_wall_seconds=parent_adapter.SELECTED_TRAJECTORY_BASELINE_SECONDS,current_iteration_observed_outer_seconds=selected['wall_accounting']['selected_checkpoint_reported_current_iteration_wall_seconds'],parent_completed_campaign_cost_baseline_seconds=parent_adapter.PRODUCING_COST_BEFORE_SECONDS,cumulative_successful_ancestor_and_completed_campaign_cost_seconds=parent_adapter.PRODUCING_COST_BEFORE_SECONDS+selected['wall_accounting']['selected_checkpoint_reported_current_iteration_wall_seconds'],model='model',optimizer={'param_groups':[{'lr':3e-5,'eps':1e-5}]},rng='rng')
        fps=selected['learner_fingerprints']
        fp=lambda value: fps['optimizer' if isinstance(value,dict) else 'model' if value=='model' else 'rng']
        old_fp=runner.fingerprint
        runner.fingerprint=fp
        runner._PARENT_METADATA_PATH=str(Path(selected['checkpoint_path']+'.json').resolve())
        runner._PARENT_COST_RECEIPT_PATH=str(build_registration.PRODUCING_COST_PATH.resolve())
        runner._LATEST_COST_RECEIPT_PATH=str(build_registration.LATEST_COST_PATH.resolve())
        try:
            runner.validate_parent_checkpoint_for_restore(state,parent_adapter.CHECKPOINT_SHA256,selected)
            bad=dict(state); bad['config_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Checkpoint differs from selected receipt'):
                runner.validate_parent_checkpoint_for_restore(bad,parent_adapter.CHECKPOINT_SHA256,selected)
        finally:
            runner.fingerprint=old_fp
    def test_schema_rejects_spec_limits_ppo_and_required_pins(self):
        reg=self.build()
        for mutate in (lambda x:x['lr_schedule'].__setitem__('spec_sha256','f'*64), lambda x:x['limits'].__setitem__('work_seconds',1791), lambda x:x['ppo'].__setitem__('update_epochs',5), lambda x:x['pins'].pop(x['runner_path'])):
            bad=copy.deepcopy(reg); mutate(bad)
            with self.assertRaises(ValueError): registration_schema.validate_identity(bad)
    def test_launcher_validates_all_sixty_metric_rows_and_rejects_corruption(self):
        metrics=[]
        for local in range(1,61):
            cumulative=372+local; lr=runner.lr_schedule.learning_rate_for_cumulative_update(cumulative)
            metrics.append({'local_update':local,'cumulative_updates':cumulative,'counters':{'updates':local},'lr_schedule':{'schedule_origin_cumulative_update':372,'horizon_updates':60,'completed_schedule_updates':local,'schedule_spec_sha256':runner.lr_schedule.SCHEDULE_SPEC_SHA256,'optimizer_param_group_count':2},'optimizer_group_lrs':[lr,lr]})
        self.assertTrue(execute_once.validate_metric_schedule(metrics))
        negatives=[]
        missing=copy.deepcopy(metrics); missing[11].pop('optimizer_group_lrs'); negatives.append(missing)
        stale=copy.deepcopy(metrics); stale[11]['optimizer_group_lrs']=[3e-5,3e-5]; negatives.append(stale)
        wrong_spec=copy.deepcopy(metrics); wrong_spec[11]['lr_schedule']['schedule_spec_sha256']='0'*64; negatives.append(wrong_spec)
        wrong_counter=copy.deepcopy(metrics); wrong_counter[11]['lr_schedule']['completed_schedule_updates']=10; negatives.append(wrong_counter)
        wrong_group=copy.deepcopy(metrics); wrong_group[11]['optimizer_group_lrs']=[wrong_group[11]['optimizer_group_lrs'][0]]; negatives.append(wrong_group)
        for rows in negatives:
            with self.assertRaises(ValueError): execute_once.validate_metric_schedule(rows)
    def test_launcher_lr_binding_at_entry_middle_and_terminal(self):
        for phase,local,cumulative,lr in ((324,0,372,3e-5),(336,12,384,3e-5-2e-5*11/59),(384,60,432,1e-5)):
            state={'phase_update':phase,'local_update':local,'update_progress':{'complete':True,'in_update':False,'completed_updates':local},'counters':{'updates':local},'cumulative_counters':{'updates':cumulative},'optimizer':{'param_groups':[{'lr':lr}]},'lr_schedule':{'schedule_origin_cumulative_update':372,'horizon_updates':60,'completed_schedule_updates':local,'schedule_spec_sha256':runner.lr_schedule.SCHEDULE_SPEC_SHA256,'optimizer_param_group_count':1}}
            execute_once.validate_terminal_candidate_binding(state,phase,{'updates':local})
            bad=copy.deepcopy(state); bad['optimizer']['param_groups'][0]['lr']=3e-5
            if phase != 324:
                with self.assertRaises(ValueError): execute_once.validate_terminal_candidate_binding(bad,phase,{'updates':local})
    def test_builder_spec_manifest_pin_rewrite_and_collision_negatives(self):
        pins={}; key=str(ROOT/'runner.py')
        build_registration._source_pin(pins,ROOT/'runner.py','a'*64)
        with self.assertRaisesRegex(ValueError,'rewrite refused'):
            build_registration._source_pin(pins,ROOT/'runner.py','b'*64)
        with self.assertRaisesRegex(ValueError,'manifest missing or digest drifted'):
            build_registration.require_manifest(ROOT/'helper-manifest.json','0'*64,'helper')
        reg=self.build(); reg['lr_schedule']['spec_sha256']='f'*64
        with self.assertRaises(ValueError): registration_schema.validate_identity(reg)
        collision=ROOT/'registration-collision-test.json'
        collision.write_text('{}\n')
        try:
            with self.assertRaises(SystemExit):
                import argparse
                args=argparse.Namespace(output=collision)
                if args.output.exists(): raise SystemExit('Refusing registration collision')
        finally: collision.unlink()
        collision.write_text('{}\n')
        try:
            cmd=[sys.executable,str(ROOT/'build_registration.py'),'--runner-manifest',str(ROOT/'runner-manifest.json'),'--runner-manifest-sha256',sha(ROOT/'runner-manifest.json'),'--helper-manifest',str(ROOT/'helper-manifest.json'),'--helper-manifest-sha256',sha(ROOT/'helper-manifest.json'),'--launcher-manifest',str(ROOT/'launcher-manifest.json'),'--launcher-manifest-sha256',sha(ROOT/'launcher-manifest.json'),'--output',str(collision)]
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0); self.assertIn('Refusing registration collision',result.stderr)
        finally: collision.unlink()
    def test_source_manifest_rewrite_and_launcher_manifest_fail_closed(self):
        r=self.build(); changed=copy.deepcopy(r); changed['pins'][changed['runner_path']]='f'*64
        with self.assertRaises(ValueError): runner.validate_registration(changed)
        with self.assertRaises(ValueError): build_registration.require_manifest(ROOT/'launcher-manifest.json','0'*64,'launcher')

if __name__=='__main__': unittest.main()
