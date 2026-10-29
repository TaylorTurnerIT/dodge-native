"""Fail-closed local binding for the parent-authorized DODGE-012 diagnostic."""
from __future__ import annotations
import hashlib,json,os,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PARENT=ROOT/'learning/runs/v2/control-frequency-confirmation-parent-20261029-r1'
PROTOCOL_PATH=PARENT/'protocol.json'
CANCEL=HERE/'cancel'
GATE_SCHEMA='control_frequency_confirmation_gate_acceptance_v1'
GATE_STATUS='parent_approved_exactly_once_frozen_policy_screen'
GATE_KEYS=('independent_source_review','native_common_runtime_and_repeat4_parity','actual_MPS_startup_qualification','checkpoint_integrity_and_frozen_weights','cohort_reservation_and_seed_exclusions','sampling_and_statistics_protocol','resource_calibration','AC_power_and_owned_caffeinate','main_lease_serialization','supervisor_cleanup','exactly_once','registration','no_optimizer_or_checkpoint_write')
class Cancelled(RuntimeError): pass

def need(ok,message):
    if not ok: raise ValueError(message)
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def read(path):
    def unique(items):
        out={}
        for k,v in items:
            need(k not in out,'duplicate JSON key: '+k);out[k]=v
        return out
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def save(path,value):
    path=Path(path);fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.link(tmp,path);dfd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:os.unlink(tmp)

def protocol():return read(PROTOCOL_PATH)
def input_pins():return protocol()['input_pins']
def source_acceptance_document(source_sha):return dict(schema='control_frequency_confirmation_source_acceptance_v1',status='accepted_source_review_only',source_manifest_sha256=source_sha)
def approval_document(reg_sha,source_sha,pins):return dict(schema=GATE_SCHEMA,status=GATE_STATUS,registration_sha256=reg_sha,source_manifest_sha256=source_sha,gates=dict.fromkeys(GATE_KEYS,'passed'),pins=pins)
def verify_pins(pins):
    need(type(pins)is dict,'pins object required')
    for path,digest in pins.items():need(sha(path)==digest,'pin drift: '+path)
def check_lease(reg):
    state=read(reg['state_path']);key=reg['lease_key']
    need(state.get(key)==reg['expected_lease'],'exact inference lease changed')
    for other in ('active_long_campaign','active_inference_campaign','active_inference_lease'):
        need(state.get(other)is None,'conflicting training/inference lease: '+other)
    need(state.get('training_hold',{}).get('active') is not True,'training hold active')
    work=state.get('control_frequency_confirmation_work');need(type(work)is dict and all(work.get(k)==v for k,v in reg['expected_parent_work_identity'].items()),'main confirmation work record changed')
    need(not os.path.lexists(CANCEL),'parent cancellation')
def load_envelope(path,digest):
    need(sha(path)==digest,'envelope digest differs');env=read(path)
    reg=read(env['registration']);need(sha(env['registration'])==env['registration_sha256'],'registration digest differs')
    need(env['registration_sha256']==env['pins'].get(env['registration']),'registration envelope pin differs')
    need(env['source_manifest_sha256']==reg['source_manifest_sha256'],'source manifest binding differs')
    verify_pins(env['pins'])
    env['path']=str(Path(path).resolve());env['sha256']=digest
    return env,reg
def verify_bound(env,reg,*,preflight):
    validate_static(reg)
    need(sha(env['registration'])==env['registration_sha256'],'registration changed')
    need(env['run_id']==reg['run_id'],'run identity differs')
    verify_pins(env['pins'])
    need(sha(reg['source_manifest_path'])==reg['source_manifest_sha256'],'source manifest changed')
    source=read(reg['source_manifest_path'])
    for name,digest in source['files'].items():need(sha(HERE/name)==digest,'source member changed: '+name)
    need(sha(reg['runtime_manifest_path'])==reg['runtime_manifest_sha256'],'runtime manifest changed')
    runtime=read(reg['runtime_manifest_path'])
    runtime_root=Path(reg['runtime_root']).resolve()
    members={str(p.relative_to(runtime_root)) for p in runtime_root.rglob('*') if p.is_file()}
    need(members==set(runtime['files']),'runtime member set differs')
    for name,digest in runtime['files'].items():
        path=runtime_root/name;need(not path.is_symlink() and sha(path)==digest,'runtime member changed: '+name)
    if preflight:check_lease(reg)

def worker_command(env,reg):
    return [reg['interpreter'],'-B',str(HERE/'worker.py'),'--envelope',env['path'],'--envelope-sha256',env['sha256']]
def worker_resources(out,*,strict=False):
    p=Path(out)/'resources.jsonl';samples=[]
    if p.exists():
        for line in p.read_text().splitlines():
            try:samples.append(json.loads(line))
            except Exception:
                if strict:raise
    return dict(samples=len(samples),peak_rss_bytes=max((x.get('rss_bytes',0) for x in samples),default=0),peak_mps_driver_bytes=max((x.get('mps_driver_bytes',0) for x in samples),default=0))

def validate_static(reg):
    p=protocol();need(reg.get('schema')=='control_frequency_confirmation_registration_v1','registration schema differs')
    need(reg.get('status')=='parent_registered' and reg.get('launch_authority') is False,'registration not parent accepted/non-authorizing')
    need(reg['run_id']==p['run_id'] and reg['expected_lease']==p['expected_lease'],'protocol/lease identity differs')
    need(reg['seeds']==p['seeds'] and reg['order']==p['order'] and reg['condition_limits']==p['condition_limits'],'cohort/order/budget differs')
    need(reg['limits']==p['limits'] and reg['controller_seeds']==p['controller_seeds'],'resource/controller contract differs')
    need(reg['checkpoint_sha256']==p['checkpoint']['sha256'] and reg['model_fingerprint']==p['checkpoint']['model_fingerprint'],'checkpoint selection differs')
    runtime_binding=read(PARENT/'runtime-binding.json')
    need(reg['runtime_manifest_sha256']==runtime_binding['runtime_manifest_sha256'] and reg['runtime_root']==runtime_binding['runtime_root'],'common successor runtime differs')
    need(reg['backend']=='mps' and reg['dtype']=='float32' and reg['torch_num_threads']==4,'inference device contract differs')
    need(reg.get('launch_authority') is False and reg.get('automatic_selection') is False and reg.get('promoted') is False,'registration grants forbidden authority')
    verify_pins(reg['input_pins'])
    expected_interpreter=ROOT/'python/.venv/bin/python'
    need(Path(reg['interpreter'])==expected_interpreter and expected_interpreter.is_absolute(),'worker interpreter path must retain project venv lexical path')
    need(sha(expected_interpreter.resolve())==reg['interpreter_sha256'] and expected_interpreter.resolve().is_file(),'worker interpreter binary changed or missing')
    seeds=reg['seeds'];seed_bytes=b''.join(int(seed).to_bytes(4,'big') for seed in seeds)
    need(hashlib.sha256(seed_bytes).hexdigest()==read(reg['cohort_reservation_path'])['seed_vector_sha256_u32be'],'reserved seed vector differs')
    need(Path(reg['output']).resolve()==(HERE/'worker-output').resolve(),'output escaped owner directory')
    need(Path(reg['attempt_claim_path']).resolve()==(HERE/'attempt.claimed').resolve(),'attempt marker path differs')
    need(Path(reg['launch_marker_path']).resolve()==(HERE/'launch.claimed').resolve(),'launch marker path differs')
    need(all(reg.get(k)is True for k in ('no_training','no_optimizer','no_checkpoint_write')),'training boundary differs')
    return True

P=protocol()
PROTOCOL=P
LIMITS=P['limits']
CONDITION_MAP={c['id']:c for c in P['conditions']}
