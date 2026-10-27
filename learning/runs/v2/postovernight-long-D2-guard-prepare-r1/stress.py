"""ONE bounded stdlib contention stress; stop at first Guard failure, no retry.

Executes the actual frozen worker verify closure and current full pins/capsule.
Legacy identity bodies are AST-extracted unchanged except removal of build_identity's
relative PPO import. Explicit static stand-ins replace cached architecture, PPO
metadata/config validation, native-extension lookup, and ML/runtime metadata.
No ML/native import, checkpoint decoding or execution is possible in this harness.
A continuous arithmetic Python thread intentionally contends for the GIL. This
is a strong synthetic scheduling scenario, not a measured ML workload replica.
"""
import ast,copy,hashlib,io,json,os,platform,sys,threading,time,types
from pathlib import Path
import long_d2 as c
import lifecycle as life
H=Path(__file__).resolve().parent;E=Path(os.environ['LONG_D2_TEST_EVIDENCE'])
MAX_SECONDS=120

def legacy_api(p,base,identity):
    source=(c.ORIGINAL_ROOT/'python/dodge_rl/identity.py').read_text();tree=ast.parse(source)
    keep={'require','canonical_bytes','identity_hash','file_hash','read_protocol','source_inventory','foundation_identity','build_identity','check_same_run','check_frozen'}
    body=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in keep:
            node=copy.deepcopy(node)
            if node.name=='build_identity':
                node.body=[ast.Pass() if isinstance(x,ast.ImportFrom) else x for x in node.body]
            body.append(node)
    foundation=identity['base_registered_identity']['foundation'];runtime=identity['base_registered_identity']['runtime']
    extension=types.SimpleNamespace(__file__=foundation['extension_path'])
    class PPO:
        def __init__(self,**kw):assert kw==base['ppo']
        def description(self):return copy.deepcopy(identity['base_registered_identity']['ppo'])
    def validate(config):assert config==base;return config
    ns=dict(Path=Path,json=json,hashlib=hashlib,copy=copy,ROOT=c.ORIGINAL_ROOT,
        PROTOCOL_PATH=Path('docs/v2-m3-run-protocol.json'),PROTOCOL_SHA256='9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab',
        GATE_SHA256='e091f8a2fad0a307d289a6d306112606b15df8f8aa0f3a75707ac7cfb2cee803',CONTRACT_SHA256='a1051d82527a9aec1f7967ff8ab217c30263240e032991aeff7b993fd975ba47',
        FOUNDATION_PATH=Path('learning/runs/v2-orchestration/milestone2-acceptance-r2.json'),FOUNDATION_IDENTITY=Path('learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json'),
        EXTENSION_SHA256=foundation['extension_sha256'],importlib=types.SimpleNamespace(import_module=lambda name:extension),PPOConfig=PPO,validate_config=validate,
        _architecture_description=lambda:copy.deepcopy(identity['base_registered_identity']['architecture']),
        sys=types.SimpleNamespace(version=runtime['python'],executable=runtime['interpreter']),
        torch=types.SimpleNamespace(__version__=runtime['torch'],backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda:runtime['mps_available']))),
        np=types.SimpleNamespace(__version__=runtime['numpy']),platform=types.SimpleNamespace(platform=lambda:runtime['platform'],machine=lambda:runtime['machine']))
    module=ast.fix_missing_locations(ast.Module(body=body,type_ignores=[]));exec(compile(module,'stdlib_legacy_identity_bodies','exec'),ns)
    (E/'legacy-executed.ast.txt').write_text(ast.dump(module,indent=2)+'\n')
    c.save(E/'legacy-substitutions.json',dict(source_sha256=c.sha(c.ORIGINAL_ROOT/'python/dodge_rl/identity.py'),
        bodies=sorted(keep),removed_import='build_identity relative .ppo only',standins=['cached architecture','PPO description','validate_config exact base equality','native extension lookup no import','fixed ML/runtime metadata'],
        no_native_ML_import_or_execution=True,legacy_internal_hashes_not_counted_in_Guard_controller_sha_totals=True))
    return types.SimpleNamespace(check_frozen=ns['check_frozen'])

def main():
    root=H/'capsule-final';p,config,base,identity,pins,lease=c.capsule_context(root)
    modules={'dodge_rl.synthetic'+str(i):types.SimpleNamespace(__file__=path) for i,path in enumerate(identity['legacy_module_origins'])}
    worker=next(n for n in ast.parse((H/'long_d2.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    node=copy.deepcopy(next(n for n in worker.body if isinstance(n,ast.FunctionDef) and n.name=='verify'))
    ns=dict(vars(c));ns.update(ROOT=root,p=p,base=base,identity=identity,pins=pins,imported={'identity':legacy_api(p,base,identity)},
        check_module_origins=lambda i,r:c.check_module_origins(i,r,modules))
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]));exec(compile(module,'actual_frozen_worker_verify','exec'),ns)
    (E/'worker-verify.ast.txt').write_text(ast.dump(module,indent=2)+'\n')
    c.save(E/'stress-registration.json',dict(max_seconds=MAX_SECONDS,full_pin_count=len(pins),full_pin_bytes=sum(Path(k).stat().st_size for k in pins),
        identity_sha256=c.sha(H/'long-identity.json'),capsule_manifest_sha256=c.sha(root/'capsule-manifest.json'),controller_sha256=c.sha(H/'long_d2.py'),
        contention='one continuous Python arithmetic thread; default GIL switch interval unchanged',switch_interval_seconds=sys.getswitchinterval(),
        origin_standins=len(modules),resource_probes='zero-valued stubs; real independent monitor/lease callback; no active campaign lease',
        same_trigger2_limit5=True,one_attempt_only=True,ML_workload_equivalence_claimed=False))
    stop=threading.Event();counter=[0]
    def burn():
        value=1
        while not stop.is_set():
            for _ in range(10000):value=(value*1664525+1013904223)&0xffffffff
            counter[0]+=10000
    # Full startup before contention, matching worker's pre-import Guard startup.
    start=time.monotonic();g=c.Guard(start+MAX_SECONDS+5,lambda:None,ns['verify'],None,rss=lambda:0,peak=lambda:0)
    cpu=None;first_failure=None;close_error=None
    try:
        g.start()
        cpu=threading.Thread(target=burn,name='synthetic-Python-CPU',daemon=True);cpu.start()
        deadline=start+MAX_SECONDS
        while time.monotonic()<deadline:
            if g.failure is not None:
                first_failure=repr(g.failure);break
            time.sleep(.01)
    except BaseException as error:first_failure=repr(error)
    finally:
        stop.set()
        if cpu is not None:cpu.join(.5)
        g.event.set()
        try:g.close()
        except BaseException as error:close_error=repr(error)
        # No retry, caps, trigger, pin-set or workload changes after a failure.
        try:g.persist_timing(E/'verification-timing.jsonl',time.monotonic()+3)
        except BaseException as error:close_error=close_error or repr(error)
        c.save(E/'stress-result.json',dict(status='failed_blocker_requires_new_design' if first_failure or close_error else 'bounded_synthetic_pass',
            first_failure=first_failure,close_error=close_error,elapsed_seconds=time.monotonic()-start,
            guard_failure_at=g.failure_at,samples=len(g.timings),successful_samples=sum(r['status']=='passed' for r in g.timings),
            background_samples=sum(r['background'] for r in g.timings),rows=g.timings,resource_receipt=g.receipt(),
            maximum_duration_seconds=max((r.get('duration_seconds',0) for r in g.timings),default=0),
            maximum_full_gap_seconds=max((r.get('full_gap_seconds',0) for r in g.timings),default=0),
            CPU_iterations=counter[0],owned_threads_absent=all(t is None or not t.is_alive() for t in (cpu,g.thread,g.verify_thread)),
            no_retry=True,ML_imports=any(n in ('torch','numpy','dodge_rl') for n in sys.modules),
            limitations=['finite synthetic sample; no population/p99.9 guarantee','continuous Python CPU is not measured production ML load','static metadata/native lookup substitutes disclosed','Guard hash counts exclude unchanged legacy file_hash internal reads']))
    if first_failure or close_error:raise SystemExit(1)

if __name__=='__main__':main()
