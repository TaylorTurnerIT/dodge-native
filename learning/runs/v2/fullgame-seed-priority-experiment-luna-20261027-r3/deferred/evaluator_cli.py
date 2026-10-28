"""Later parent-registered full-run evaluator; no study execution in preparation."""
from __future__ import annotations
import argparse
import copy
import importlib
import random
from pathlib import Path
import resource
import sys
import time

import contracts as c
from expanded_eval import POLICY_IDS, _production_rows, compare, summarize

EVAL_FIELDS={'schema','status','study_id','backend','runtime_versions','runtime_manifest_sha256',
             'source_manifest_sha256','input_manifest_sha256','cohort_state','history_state','reservation_state',
             'seeds','exclusion_union','evaluation_rng_seed','action_mode','cutoff_enabled','normal_start',
             'row_count','policies','limits','output_root','claim_root','state_path','expected_lease',
             'import_policy','interpreter'}


def validate_evaluation(reg):
    c.need(type(reg)is dict and set(reg)==EVAL_FIELDS,'evaluation registration fields differ')
    c.need(reg['schema']=='progressive1000_evaluation_registration_v1' and reg['status']=='parent_registered'
         and reg['study_id']==c.STUDY,'evaluation template is inert')
    c.need(reg['cohort_state']=='reserved_parent_approved' and reg['history_state']=='freshness_parent_approved'
         and reg['reservation_state']=='parent_reserved','pending evaluation cohort/history/reservation')
    c.need(reg['backend']=='mps' and reg['action_mode']=='sampled_categorical'
         and reg['cutoff_enabled'] is False and reg['normal_start'] is True and reg['row_count']==1024,
         'full normal-start sampled-action/backend/cutoff/row-count pin differs')
    seeds=reg['seeds']
    c.need(type(seeds)is list and seeds==list(range(0xD3000000,0xD3000400)), 'exact shared new1024 cohort required')
    c.validate_union(reg['exclusion_union'])
    c.need(type(reg['evaluation_rng_seed'])is int and 0<reg['evaluation_rng_seed']<2**63,'parent evaluation RNG seed missing')
    manifest=c.verify_inputs()
    c.need(c.sha(c.HERE/'input-manifest.json')==reg['input_manifest_sha256'],'evaluation input manifest differs')
    c.need(reg['runtime_versions']==manifest['runtime_versions'],'evaluation dependency versions differ')
    c.verify_manifest(c.HERE/'source-manifest.json',reg['source_manifest_sha256'],c.HERE)
    c.verify_manifest(c.HERE/'runtime-manifest.json',reg['runtime_manifest_sha256'],c.HERE/'runtime',exact=True)
    policies=reg['policies']
    c.need(type(policies)is list and [p.get('id') for p in policies]==list(POLICY_IDS),'fixed six terminal endpoints plus one shared parent required')
    for policy in policies:
        c.need(set(policy)=={'id','checkpoint_path','checkpoint_sha256','worker_result_path','worker_result_sha256'},'policy fields differ')
        c.need(c.sha(policy['checkpoint_path'])==policy['checkpoint_sha256'],'evaluation checkpoint bytes drift')
        if policy['id']=='parent324':
            c.need(policy['checkpoint_sha256']==c.references.ACCEPTED_CHECKPOINT_SHA256
                 and policy['worker_result_path'] is None and policy['worker_result_sha256'] is None,'shared accepted parent differs')
        else:
            c.need(c.sha(policy['worker_result_path'])==policy['worker_result_sha256'],'terminal worker result drift')
            result=c.read(policy['worker_result_path'])
            endpoint=result.get('formal_comparison_endpoint',{})
            c.need(result.get('status')=='completed' and result.get('updates')==60
                 and result.get('run_id')==c.STUDY+'-'+policy['id']
                 and endpoint.get('sha256')==policy['checkpoint_sha256']
                 and endpoint.get('global_update')==60 and endpoint.get('formal_comparison_endpoint') is True,
                 'policy is not predetermined terminal60 endpoint')
    c.need(type(reg['limits'])is dict and set(reg['limits'])=={'wall_seconds','rss_bytes','mps_bytes','raw_frames'}
         and all(type(v)is int and v>0 for v in reg['limits'].values()),'evaluation resources unmeasured/missing')
    for key in ('output_root','claim_root'):
        path=Path(reg[key]);c.need(path.is_absolute() and path.is_dir(),'parent must prepare evaluation '+key)
    c.need(c.read(reg['state_path']).get('active_long_campaign')==reg['expected_lease']
         and reg['expected_lease'] is not None,'evaluation parent lease changed')
    c.cache_check(reg)
    return reg


def preflight(path,digest,approval_path,approval_sha,policy_id):
    c.need(c.sha(path)==digest and c.sha(approval_path)==approval_sha,'evaluation external gate SHA differs')
    reg=validate_evaluation(c.read(path))
    c.need(policy_id in POLICY_IDS,'unregistered endpoint')
    c.need(c.read(approval_path)==dict(schema='progressive1000_evaluation_launch_approval_v1',
         status='approved_exactly_one_fixed_endpoint',registration_sha256=digest,policy_id=policy_id,
         gates=dict.fromkeys(c.GATES,'passed')),'parent evaluation approval missing')
    out=Path(reg['output_root'])/(policy_id+'.json')
    c.need(not out.exists() and not Path(str(out)+'.events.jsonl').exists(),'evaluation output already spent')
    c.need(not (Path(reg['claim_root'])/(policy_id+'.claim')).exists(),'evaluation claim already spent')
    return reg


def evaluate_registered(reg,policy_id,registration_sha):
    """Concrete common model/native evaluator. Caller has completed preflight."""
    from attempt_claim import AttemptClaim
    from fingerprints import fingerprint
    from worker import emit, save
    from death_telemetry import death_fields
    c.need(not any(name=='dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),'evaluation runtime must start unloaded')
    policy=next(p for p in reg['policies'] if p['id']==policy_id)
    # Spend once before any deserialization, initialization, reseeding or game.
    AttemptClaim(Path(reg['claim_root'])/(policy_id+'.claim'),dict(run_id=c.STUDY+'-eval-'+policy_id,
        study_id=c.STUDY,replica=1 if policy_id=='parent324' else int(policy_id.split('-')[1]),arm=policy_id,
        vector_sha256=__import__('hashlib').sha256(c.canonical(reg['seeds'])).hexdigest(),
        parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256)).claim()
    sys.path.insert(0,str(c.HERE/'runtime'))
    np=importlib.import_module('numpy');torch=importlib.import_module('torch')
    game=importlib.import_module('dodge_rl');ckpt=importlib.import_module('dodge_rl.checkpoints')
    teacher=importlib.import_module('dodge_rl.models.teacher')
    from runtime_adapter import authenticate_module,authenticate_class
    import driver_binding as binding
    authenticate_module(ckpt,'dodge_rl/checkpoints.py',binding.CHECKPOINT_FUNCTIONS+('load_checkpoint','save_checkpoint','episode_resume_state','_cpu_copy'))
    authenticate_class(teacher,'OmniscientEntityTeacher');authenticate_class(teacher,'CustomTransformerLayer')
    c.need(dict(python=sys.version.split()[0],numpy=str(np.__version__),torch=str(torch.__version__))==reg['runtime_versions'],
           'loaded evaluation dependencies differ')
    c.need(torch.backends.mps.is_available(),'evaluation MPS unavailable')
    runtime_manifest=c.read(c.HERE/'runtime-manifest.json')
    for name,module in tuple(sys.modules.items()):
        if name=='dodge_rl' or name.startswith('dodge_rl.'):
            path=Path(module.__file__).resolve();c.need(path.is_relative_to(c.HERE/'runtime'),'evaluation loaded origin differs')
            c.need(c.sha(path)==runtime_manifest['files'].get(str(path.relative_to(c.HERE/'runtime'))),'evaluation loaded member/native differs')
    state=ckpt.load_checkpoint(Path(policy['checkpoint_path']),expected_sha256=policy['checkpoint_sha256'])
    ckpt.require_complete_update(state)
    if policy_id=='parent324':
        c.need(fingerprint(state['model'])==c.transition.EXPECTED_PARENT['model'],'accepted parent model fingerprint differs')
    else:
        identity=state['identity']
        c.need(state['schema']=='progressive1000_integrity_checkpoint_v1' and state['global_update']==60
             and state['phase_update']==384 and state['cumulative_update']==432
             and identity['run_id']==c.STUDY+'-'+policy_id
             and identity['backend']==reg['backend']
             and identity['successor_runtime']['runtime_manifest_sha256']==reg['runtime_manifest_sha256']
             and identity['successor_runtime']['source_manifest_sha256']==reg['source_manifest_sha256'],
             'terminal checkpoint identity differs')
    rng=ckpt.capture_rng('mps'); grad_enabled=torch.is_grad_enabled()
    output=Path(reg['output_root'])/(policy_id+'.json');started=time.monotonic();cost=[0]
    with Path(str(output)+'.events.jsonl').open('x') as events:
        def guard():
            c.need(time.monotonic()-started<=reg['limits']['wall_seconds'],'evaluation wall ceiling')
            rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)
            c.need(rss<=reg['limits']['rss_bytes'] and torch.mps.driver_allocated_memory()<=reg['limits']['mps_bytes'],'evaluation memory ceiling')
            c.need(cost[0]<=reg['limits']['raw_frames'],'evaluation raw-frame ceiling')
            c.need(c.read(reg['state_path']).get('active_long_campaign')==reg['expected_lease'],'evaluation lease changed')
        def journal(event):
            if event['kind']=='evaluation_constructor':cost[0]+=event['info']['startup_frames']
            if event['kind']=='evaluation_step':cost[0]+=event['elapsed_raw_frames']
            emit(events,event)
        try:
            guard()
            model=teacher.OmniscientEntityTeacher().to('mps');model.load_state_dict(state['model'],strict=True);model.eval()
            model._expanded_eval_device='mps';before=fingerprint(model.state_dict())
            # Explicit, common parent-registered sampling stream. Sampling consumes
            # this scratch stream, then the caller's complete RNG state is restored.
            random.seed(reg['evaluation_rng_seed']);np.random.seed(reg['evaluation_rng_seed']%(2**32))
            torch.manual_seed(reg['evaluation_rng_seed']);torch.mps.manual_seed(reg['evaluation_rng_seed'])
            rng_before=fingerprint(ckpt.capture_rng('mps'))
            # Training union excludes the evaluated cohort. Evaluation removes only
            # that one cohort from exclusions, retaining every historical range.
            excluded=[]
            for low,high in reg['exclusion_union']:
                if low<0xD3000000:excluded.append((low,min(high,0xD3000000-1)))
                if high>0xD30003FF:excluded.append((max(low,0xD3000400),high))
            rows=_production_rows(model,game.VecDodgeEnv,tuple(__import__('successor_identity').NEURAL_INPUTS),
                death_fields,reg['seeds'],excluded,guard,batch_size=64,event_sink=journal)
            summary=summarize(rows,reg['seeds'])
            c.need(fingerprint(model.state_dict())==before,'evaluation changed policy weights')
            c.need(c.sha(policy['checkpoint_path'])==policy['checkpoint_sha256'],'checkpoint changed during inference')
            guard()
            result=dict(schema='progressive1000_fixed_endpoint_evaluation_v1',policy_id=policy_id,
                registration_sha256=registration_sha,checkpoint_sha256=policy['checkpoint_sha256'],
                runtime_manifest_sha256=reg['runtime_manifest_sha256'],backend=reg['backend'],action_mode=reg['action_mode'],
                cutoff_enabled=False,normal_start=True,summary=summary,rows=rows,raw_frames_including_startup=cost[0],
                scratch_rng_before_sha256=rng_before,scratch_rng_after_sha256=fingerprint(ckpt.capture_rng('mps')),
                elapsed_seconds=time.monotonic()-started,automatic_selection=False,promoted=False)
            save(output,result)
            return result
        except BaseException as error:
            emit(events,dict(kind='evaluation_failure',error=repr(error),raw_frames_including_startup=cost[0],complete=False,no_retry=True))
            raise
        finally:
            ckpt.restore_rng(rng,'mps')
            c.need(fingerprint(ckpt.capture_rng('mps'))==fingerprint(rng),'evaluation failed to restore caller RNG')
            c.need(torch.is_grad_enabled()==grad_enabled,'evaluation changed global gradient mode')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',required=True);parser.add_argument('--registration-sha256',required=True)
    parser.add_argument('--parent-approval',required=True);parser.add_argument('--parent-approval-sha256',required=True)
    parser.add_argument('--policy',required=True,choices=POLICY_IDS)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    reg=preflight(args.registration,args.registration_sha256,args.parent_approval,args.parent_approval_sha256,args.policy)
    if not args.validate_only:evaluate_registered(reg,args.policy,args.registration_sha256)
    return 0


if __name__=='__main__':raise SystemExit(main())
