#!/usr/bin/env python3
"""Build same-LR registration after parent assembles and freezes components."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[4] / "learning/runs/v2/D2-retained300-continuation-parent-integration-20261026-r5" / "integration-contract.json"
ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
BASE_DEFAULT = ROOT / "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--final-source-dir', type=Path)
    ap.add_argument('--base-registration', type=Path, default=BASE_DEFAULT)
    ap.add_argument('--output', type=Path, default=OWN/'registration-proposal.json')
    args=ap.parse_args()
    c=json.loads(CONTRACT.read_text())
    final=(args.final_source_dir or Path(c['final_source_dir'])).resolve()
    required=['runner.py','execute_once.py','registration_schema.py','parent_adapter.py']
    missing=[name for name in required if not (final/name).is_file()]
    if missing: raise SystemExit('refusing: assembled sources missing: '+', '.join(missing))
    if not args.base_registration.is_file(): raise SystemExit(f'refusing: base registration missing: {args.base_registration}')
    out=args.output.resolve()
    if out != OWN/'registration-proposal.json' and final not in out.parents:
        raise SystemExit('refusing: output must be own directory or inside final source directory')
    reg=json.loads(args.base_registration.read_text())
    selected_receipt=ROOT/'learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-candidate-receipt.json'
    if not selected_receipt.is_file() or sha(selected_receipt)!=c['selected_receipt_sha256']:
        raise SystemExit('refusing: selected parent receipt missing or hash differs')
    selected=json.loads(selected_receipt.read_text())
    if sha(args.base_registration)!=selected['registration_sha256']:
        raise SystemExit('refusing: base registration is not the selected checkpoint registration')
    verified=[(Path(selected['checkpoint_path']), selected['checkpoint_sha256']),
      (Path(selected['checkpoint_path']+'.json'), selected['checkpoint_sidecar_sha256']),
      (Path(selected['evaluation_path']), selected['evaluation_sha256']),
      (Path(selected['evaluation_jsonl_path']), selected['evaluation_jsonl_sha256']),
      (Path(selected['completed_iteration_receipt_path']), c['completed_cost_receipt_sha256'])]
    for path,expected in verified:
        if not path.is_file() or sha(path)!=expected:
            raise SystemExit(f'refusing: selected parent input missing or hash differs: {path}')
    reg.update(schema=c['schema'], transition_schema=c['transition_schema'], run_id=c['run_id'],
      run_seed=c['run_seed'], phase_start=c['phase_start'], phase_end=c['phase_end'],
      expected_total_updates=c['expected_total_updates'], new_updates=c['new_updates'], parent_total_updates=c['parent_total_updates'],
      output=c['actual_output'], config_sha256=c['config_sha256'], training_eligible=False, promoted=False)
    for key,name in [('runner_path','runner.py'),('launcher_path','execute_once.py'),('registration_schema_module_path','registration_schema.py')]:
        reg[key]=str(final/name)
    reg['registration_schema_module_sha256']=sha(final/'registration_schema.py')
    config=Path(reg['config_path'])
    if not config.is_file() or sha(config)!=c['config_sha256']:
        raise SystemExit('refusing: same-LR config bytes do not match immutable contract hash')
    reg['runner_sha256']=sha(final/'runner.py')
    reg['launcher_sha256']=sha(final/'execute_once.py')
    reg['parent_adapter_path']=str(final/'parent_adapter.py')
    reg['parent_adapter_sha256']=sha(final/'parent_adapter.py')
    reg['parent'].update(path=str(ROOT/'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r5/checkpoint-000348-candidate.pt'),
      checkpoint_sha256=c['parent_checkpoint_sha256'], terminal_receipt_sha256=c['selected_receipt_sha256'],
      registration_sha256='8e17e118')
    reg['pins'][str(checkpoint)]=c['parent_checkpoint_sha256']
    reg['pins'][str(checkpoint)+'.json']=selected['checkpoint_sidecar_sha256']
    reg['pins'][selected['evaluation_path']]=selected['evaluation_sha256']
    reg['pins'][selected['evaluation_jsonl_path']]=selected['evaluation_jsonl_sha256']
    reg['pins'][str(selected_receipt)]=c['selected_receipt_sha256']
    reg['pins'][str(ROOT/'learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/completed-iteration-receipt.json')]=c['completed_cost_receipt_sha256']
    reg['resource_cost_anchor']={'authority':'resource_cost_only; no model or continuation authority',
      'path':str(ROOT/'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r5/completed-iteration-receipt.json'),
      'sha256':c['completed_cost_receipt_sha256']}
    reg['limits']={'work_seconds':c['work_seconds'],'total_seconds':c['outer_seconds'],
      'RSS_bytes':c['RSS_bytes'],'MPS_bytes':c['MPS_bytes']}
    reg['evaluation_updates']=c['evaluation_updates']
    reg['expected_outputs']=[x for x in reg.get('expected_outputs',[]) if x not in ('lr-transition.json',) and not any(f'{u:06d}' in x for u in (276,288,300,312,324,336))]
    reg['expected_outputs'] += ['entry-restoration.json']
    for update in c['evaluation_updates']:
        reg['expected_outputs'] += [f'checkpoint-{update:06d}-candidate.pt', f'checkpoint-{update:06d}-candidate.pt.json', f'development-{update:06d}.json', f'development-{update:06d}.jsonl']
    reg['expected_outputs']=list(dict.fromkeys(reg['expected_outputs']))
    reg['forbidden_outputs']=sorted(set(reg.get('forbidden_outputs',[])+['lr-transition.json']))
    # Retain all prior runtime/dependency/archival pins. Replace only launcher-component authority pins.
    pins=reg.setdefault('pins',{})
    old_component=ROOT/'learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2'
    for name in ('runner.py','execute_once.py','registration_schema.py','parent_adapter.py','lr_transition.py'):
        pins.pop(str(old_component/name),None)
    for name in required: pins[str(final/name)]=sha(final/name)
    reg['limits'].update(work_seconds=c['work_seconds'], total_seconds=c['outer_seconds'], max_updates=c['new_updates'], eval_updates=c['evaluation_updates'])
    reg['resource_estimate'].update(cleanup_reserve_seconds=c['cleanup_seconds'], hard_work_cap_seconds=c['work_seconds'],
      outer_cap_seconds=c['outer_seconds'], preregistered_work_seconds=c['planned_seconds'],
      observed_control_outer_seconds=1502.5562572500203, scaled_seconds=1727.9396958375232,
      extra_planning_margin_seconds=22.06030416247677, relaxation_permitted=False)
    reg['parent_registration_sha256']=selected['registration_sha256']
    reg['parent_config_sha256']=c['config_sha256']
    reg['parent_config_path']=str(config)
    reg['cancel_path']=str(Path(c['actual_output'])/'cancel.json')
    reg.pop('arm_transition',None)
    reg['import_policy']['pycache_prefix']=str(OWN/'empty-pycache')
    reg['arm_transition']={'schema':c['transition_schema'],'learning_rate':c['learning_rate'],'changed_fields':[]}
    reg.pop('lr_transition_helper_path',None); reg.pop('lr_transition_helper_sha256',None)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(reg,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'output':str(out),'sha256':sha(out),'source_dir':str(final),'source_pins_added':required},indent=2))
if __name__=='__main__': main()
