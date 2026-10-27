from pathlib import Path
p=Path(__file__).with_name('runner.py'); s=p.read_text()
s=s.replace('PARENT_REGISTRATION_SHA = "8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7"','PARENT_REGISTRATION_SHA = "8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79"')
s=s.replace('PARENT_SOURCE_REGISTRATION_SHA = "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"','PARENT_SOURCE_REGISTRATION_SHA = "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"')
s=s.replace('PARENT_ADAPTER_SHA = "a969f2a5e6af35609f0b2cc9fb4a2f4cd1b369743a1d1cb7ba6c345355a6f2f6"','PARENT_ADAPTER_SHA = "__ADAPTER_SHA__"')
s=s.replace('D2-retained300-continuation-freeze-20261026-r5','D2-retained324-continuation-prepare-luna-20261026-r1')
s=s.replace('PARENT_SELECTED_TRAJECTORY_REPORTED_SECONDS = 5190.209660791156','PARENT_SELECTED_TRAJECTORY_REPORTED_SECONDS = 5678.9823631240915').replace('PARENT_SELECTED_ITERATION_REPORTED_SECONDS = 430.1472566659795','PARENT_SELECTED_ITERATION_REPORTED_SECONDS = 488.7727023329353')
s=s.replace('PARENT_WORKER_TRAJECTORY_REPORTED_SECONDS = 6258.458489500165','PARENT_WORKER_TRAJECTORY_REPORTED_SECONDS = 6323.834494166139').replace('PARENT_WORKER_CAMPAIGN_REPORTED_SECONDS = 8617.17817400011','PARENT_WORKER_CAMPAIGN_REPORTED_SECONDS = 9754.963179250124')
s=s.replace('SELECTED_TRAJECTORY_BASELINE_SECONDS = 5190.209660791156','SELECTED_TRAJECTORY_BASELINE_SECONDS = 5678.9823631240915').replace('COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS = 8621.338345875141','COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS = 9758.365427209174')
s=s.replace('PHASE_START = 300','PHASE_START = 324').replace('PHASE_END = 360','PHASE_END = 384').replace('PARENT_TOTAL_UPDATES = 348','PARENT_TOTAL_UPDATES = 372').replace('EXPECTED_TOTAL = 408','EXPECTED_TOTAL = 432')
s=s.replace('and EVALUATION_UPDATES == (300, 312, 324, 336, 348, 360)','and EVALUATION_UPDATES == (324, 336, 348, 360, 372, 384)')
s=s.replace('1502.5562572500203','1137.0270813340321').replace('1727.9396958375232','1307.5811435341368')
s=s.replace('"scaled_seconds"','"scaled_seconds"')
s=s.replace('reg.get("run_seed")==4200000000','reg.get("run_seed")==4200000001')
s=s.replace('parent.get("phase_update")==300','parent.get("phase_update")==324').replace('"phase_update")==300','"phase_update")==324')
s=s.replace('D2-retained276-lr3em5-20261026-r2/checkpoint-000300-candidate.pt','D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt')
s=s.replace('receipt.get("candidate_phase_update") == PHASE_START','receipt.get("candidate_phase_update") == PHASE_START')
# Replace selected-parent terminal audit function with receipt-bound exact evidence checks.
a=s.index('def validate_parent_terminal_receipt('); b=s.index('\ndef validate_capsule_support(',a)
fn='''def validate_parent_terminal_receipt(receipt, reg):
    """Validate accepted selected324 receipt and producing-run audit lineage."""
    parent=reg["parent"]
    need(receipt.get("schema")==parent_adapter.SCHEMA and receipt.get("status")==parent_adapter.STATUS
         and receipt.get("checkpoint_sha256")==PARENT_SHA and receipt.get("candidate_phase_update")==324
         and receipt.get("candidate_local_update")==24 and receipt.get("config_sha256")==CONFIG_SHA
         and receipt.get("effective_learning_rate")==LEARNING_RATE, "Selected324 receipt authority differs")
    need(sha(parent["terminal_receipt_path"])==PARENT_RECEIPT_SHA
         and receipt.get("registration_sha256")==PARENT_REGISTRATION_SHA
         and receipt.get("run_id")=="D2-retained300-continuation-20261026-r1", "Selected receipt producing-run identity differs")
    cost_path=receipt["completed_iteration_receipt_path"]; metadata_path=receipt["checkpoint_path"]+".json"
    need(cost_path==parent["completed_cost_receipt_path"] and metadata_path==parent["metadata_path"]
         and sha(cost_path)==parent["completed_cost_receipt_sha256"] and sha(metadata_path)==parent["metadata_sha256"]
         and receipt.get("completed_iteration_receipt_sha256")==parent["completed_cost_receipt_sha256"], "Selected metadata or completed-cost receipt changed")
    cost=read(cost_path); parent_adapter.validate_cost_anchor(cost,parent_adapter.COST_RECEIPT_SHA)
    audit_path=parent["audit_path"]
    need(sha(audit_path)==parent["audit_sha256"], "Parent terminal audit changed")
    audit=read(audit_path)
    need(audit.get("schema")=="d2_same_lr_parent_terminal_audit_v1" and audit.get("status")=="accepted_completed_iteration_and_selected_intermediate324"
         and audit.get("selected_update")==324 and audit.get("registration_sha256")==PARENT_REGISTRATION_SHA
         and audit.get("selected_cumulative_counters")==receipt.get("candidate_cumulative_counters"), "Accepted parent audit differs")
    full=read(parent["full_audit_path"])
    need(sha(parent["full_audit_path"])==parent["full_audit_sha256"] and full.get("audit",{}).get("updates_audited")==[300,312,324,336,348,360], "Full candidate audit differs")
    worker=read(parent["producing_worker_result_path"])
    need(sha(parent["producing_worker_result_path"])==parent["producing_worker_result_sha256"] and worker.get("status")=="completed", "Producing worker receipt differs")
    wall=receipt["wall_accounting"]
    global _PARENT_CLOCKS
    _PARENT_CLOCKS={"parent_selected_trajectory":wall["selected_checkpoint_reported_trajectory_wall_seconds"],
      "parent_selected_iteration":wall["selected_checkpoint_reported_iteration_wall_seconds"],
      "parent_worker_trajectory_end":worker["cumulative_selected_checkpoint_trajectory_wall_seconds"],
      "parent_worker_campaign_cost":worker["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"],
      "new_selected_trajectory_baseline":wall["future_checkpoint_trajectory_baseline_seconds"],
      "new_campaign_cost_baseline":cost["wall_accounting"]["completed_campaign_resource_cost_after_seconds"]}
    need(_PARENT_CLOCKS=={"parent_selected_trajectory":PARENT_SELECTED_TRAJECTORY_REPORTED_SECONDS,
      "parent_selected_iteration":PARENT_SELECTED_ITERATION_REPORTED_SECONDS,"parent_worker_trajectory_end":PARENT_WORKER_TRAJECTORY_REPORTED_SECONDS,
      "parent_worker_campaign_cost":PARENT_WORKER_CAMPAIGN_REPORTED_SECONDS,"new_selected_trajectory_baseline":SELECTED_TRAJECTORY_BASELINE_SECONDS,
      "new_campaign_cost_baseline":COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS}, "Selected receipt or producing worker clocks differ")
    for pk,dk in (("decision_path","decision_sha256"),("registration_path","registration_sha256"),
                  ("source_evaluation_path","source_evaluation_sha256"),("source_evaluation_jsonl_path","source_evaluation_jsonl_sha256")):
        need(sha(parent[pk])==parent[dk],"Parent evidence changed: "+pk)
    decision=read(parent["decision_path"])
    need(decision.get("checkpoint_sha256")==PARENT_SHA and decision.get("receipt_sha256")==PARENT_RECEIPT_SHA
         and decision.get("phase_update")==324 and decision.get("endpoint360_not_selected") is True,"Selected324 decision differs")
    producing=read(parent["registration_path"])
    need(producing.get("run_id")=="D2-retained300-continuation-20261026-r1" and sha(parent["registration_path"])==PARENT_REGISTRATION_SHA,
         "Producing registration differs")
    ev=read(parent["source_evaluation_path"])
    need(ev.get("phase_update")==324 and ev.get("local_update")==24 and ev.get("checkpoint_sha256")==PARENT_SHA
         and ev.get("evaluation",{}).get("complete") is True,"Selected evaluation differs")
    need(receipt.get("evaluation_path")==parent["source_evaluation_path"] and receipt.get("evaluation_jsonl_path")==parent["source_evaluation_jsonl_path"]
         and receipt.get("evaluation_sha256")==parent["source_evaluation_sha256"] and receipt.get("evaluation_jsonl_sha256")==parent["source_evaluation_jsonl_sha256"],
         "Receipt does not bind evaluation artifacts")
    return receipt
'''
s=s[:a]+fn+s[b:]
p.write_text(s)
# schema identity
p=Path(__file__).with_name('registration_schema.py'); p.write_text('''"""Shared D2 retained324 continuation identity check."""\nfrom pathlib import Path\nSCHEMA = "d2_retained324_same_lr_registration_v1"\nRUN_ID = "D2-retained324-continuation-20261026-r1"\ndef validate_identity(reg):\n    if not isinstance(reg,dict) or reg.get("schema")!=SCHEMA: raise ValueError("Wrong registration schema")\n    if reg.get("run_id")!=RUN_ID: raise ValueError("Wrong registration run identity")\n    root=Path(reg.get("root","")).resolve(); output=Path(reg.get("output","")).resolve()\n    if output!=root/"learning/runs/v2"/RUN_ID: raise ValueError("Unsafe registration output identity")\n    return reg\n''')
