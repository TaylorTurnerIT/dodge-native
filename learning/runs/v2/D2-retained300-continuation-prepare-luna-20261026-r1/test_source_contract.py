from pathlib import Path
import json,sys
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
reg=json.loads((OUT/'registration.json').read_text())
source=(OUT/'runner.py').read_text()
assert runner.PHASE_START==276 and runner.PHASE_END==348
assert runner.EVALUATION_UPDATES==(276,288,300,312,324,336,348)
assert runner.NEW_UPDATES==72 and runner.EXPECTED_TOTAL==396 and reg['run_seed']==3791628419
assert reg['parent']['sha256']==runner.PARENT_SHA=='e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710'
assert reg['parent']['terminal_receipt_sha256']==runner.PARENT_RECEIPT_SHA
assert reg['config_sha256']==reg['parent_config_sha256']=='1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8'
assert runner.SELECTED_TRAJECTORY_BASELINE_SECONDS==4760.062404125177
assert runner.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS==5537.773026792208
assert runner.PARENT_WHOLE_ITERATION_SECONDS==1408.0161675000563
assert 'apply_resume_lr_override' not in source and 'lr_transition_helper' not in source
assert 'optimizer = torch.optim.Adam(model.parameters(), lr=0.00003' in source
restore=source.index('ckpt.restore_learner(parent, model, optimizer, "mps")')
env=source.index('env = dodge_rl.VecDodgeEnv')
entry=source.index('evaluate_at(PHASE_START)')
update=source.index('collection = collect_rollout')
assert restore<env<entry<update
assert 'validate_entry_evaluation(evaluation, predecessor)' in source
assert 'assert_effective_lr(optimizer, 0.00003)' in source and 'assert_saved_optimizer_lr(state, 0.00003)' in source
print('source contract: exact phase-276 parent, unchanged config, restored LR, pre-gradient 64-row entry gate, and distinct wall baselines passed')
