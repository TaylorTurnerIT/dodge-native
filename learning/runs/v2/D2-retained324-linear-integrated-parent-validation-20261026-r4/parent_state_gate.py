import hashlib,json,pathlib,sys
ROOT=pathlib.Path.cwd();SOURCE=ROOT/'learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4';OUT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
import runner,parent_adapter,registration_schema
import torch
torch.set_num_threads(1)
reg_path=SOURCE/'registration-final-r2.json';reg=json.loads(reg_path.read_text())
assert hashlib.sha256(reg_path.read_bytes()).hexdigest()=='0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e'
runner.validate_registration(reg);registration_schema.validate_identity(reg)
selected=json.loads(pathlib.Path(reg['parent']['terminal_receipt_path']).read_text())
runner.validate_parent_terminal_receipt(selected,reg)
runner._PARENT_METADATA_PATH=str(pathlib.Path(reg['parent']['metadata_path']).resolve())
runner._PARENT_COST_RECEIPT_PATH=str(pathlib.Path(reg['parent']['completed_cost_receipt_path']).resolve())
runner._LATEST_COST_RECEIPT_PATH=str(pathlib.Path(reg['resource_cost_anchor']['path']).resolve())
for path,expected in ((reg['parent']['path'],runner.PARENT_SHA),(runner._LATEST_COST_RECEIPT_PATH,parent_adapter.LATEST_COST_RECEIPT_SHA256)):
 assert runner.sha(path)==expected
runner.validate_resource_cost_anchor_path(reg['resource_cost_anchor']['path'],reg['resource_cost_anchor']['sha256'])
parent=torch.load(reg['parent']['path'],map_location='cpu',weights_only=False)
runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,selected)
assert parent['cumulative_counters']['updates']==372
assert runner._PARENT_CLOCKS['new_campaign_cost_baseline']==10824.835578584221
assert runner._PARENT_CLOCKS['new_selected_trajectory_baseline']==5678.9823631240915
receipt={'status':'passed_real_CPU_parent_checkpoint_gate','actual_model_Adam_RNG_fingerprints_validated':True,'checkpoint_sha256':runner.PARENT_SHA,'candidate_phase_update':parent['phase_update'],'cumulative_updates':parent['cumulative_counters']['updates'],'latest_resource_cost':runner._PARENT_CLOCKS['new_campaign_cost_baseline'],'selected_trajectory':runner._PARENT_CLOCKS['new_selected_trajectory_baseline'],'full_load_registration_executed':False,'lease_check_mocked':False,'lease_accessed':False,'MPS_used':False,'environment_constructed':False,'training_launched':False}
(OUT/'real-parent-state-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
