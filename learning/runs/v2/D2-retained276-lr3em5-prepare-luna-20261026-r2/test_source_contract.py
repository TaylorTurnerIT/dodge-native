from pathlib import Path
import json,sys
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
reg=json.loads((OUT/'registration.json').read_text())
source=(OUT/'runner.py').read_text()
assert runner.PHASE_START==276 and runner.PHASE_END==336
assert runner.EVALUATION_UPDATES==(276,288,300,312,324,336)
assert runner.NEW_UPDATES==60 and runner.EXPECTED_TOTAL==384 and reg['run_seed']==3791628420
assert reg['parent']['sha256']==runner.PARENT_SHA=='0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292'
assert reg['parent']['terminal_receipt_sha256']==runner.PARENT_RECEIPT_SHA=='d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4'
assert reg['config_sha256']==runner.CONFIG_SHA and reg['parent_config_sha256']==runner.PARENT_CONFIG_SHA
assert reg['resource_cost_anchor']['sha256']=='711b2949fb4123381d9af6618e47f4628540f424a0973785bb6392e14169b4c3'
assert runner.SELECTED_TRAJECTORY_BASELINE_SECONDS==4760.062404125177
assert runner.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS==7118.78208862512
assert runner.LIMITS['max_updates']==60 and runner.LIMITS['work_seconds']==1790 and runner.LIMITS['total_seconds']==1800
assert reg['lr_transition_helper_path'] in reg['pins'] and reg['pins'][reg['lr_transition_helper_path']]==reg['lr_transition_helper_sha256']
assert 'load_verified_transition(reg)' in source and 'transition_helper.apply_resume_lr_override' in source
assert source.index('ckpt.restore_learner(parent, model, optimizer, "mps")') < source.index('transition_helper.apply_resume_lr_override') < source.index('env = dodge_rl.VecDodgeEnv')
assert 'validate_entry_evaluation(evaluation, predecessor)' in source
assert 'transition_helper.guarded_update(optimizer, 0.00003' in source
execution=(OUT/'execute_once.py').read_text()
assert 'Registered parent-to-arm learning-rate transition receipt differs' in execution
launcher=(OUT/'execute_once.py').read_text()
assert 'reg["interpreter"], "-B", reg["runner_path"]' in launcher
assert '"--registration-sha256", registration_sha' in launcher
assert 'env["PYTHONPYCACHEPREFIX"] = reg["import_policy"]["pycache_prefix"]' in launcher
assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in launcher
print('source contract: exact phase-276 authority, 60/6 boundaries, LR transition, pins, and budgets passed')
