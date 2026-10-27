"""One-shot RNG reference worker CLI. Production imports occur after byte/path gates."""
import argparse,hashlib,json,os,sys,threading,time
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def j(path): return json.loads(Path(path).read_text())
def check(regpath,regsha,reg,workerpath):
    global probe
    if sha(regpath)!=regsha: raise RuntimeError('registration hash drift')
    if reg.get('schema')!='d2_layerb_rng_reference_probe_registration_v1': raise RuntimeError('registration schema mismatch')
    if reg.get('_external_registration_sha256') not in (None,regsha): raise RuntimeError('registration external hash mismatch')
    for n in ('worker','supervisor','probe','fingerprint'):
        p=reg['source'][n+'_path']; h=reg['source'][n+'_sha256']
        if Path(p).absolute()!=Path({'worker':workerpath,'supervisor':Path(__file__).with_name('supervisor_cli.py'),'probe':Path(__file__).with_name('probe.py'),'fingerprint':reg['source']['fingerprint_path']}[n]).absolute() or sha(p)!=h: raise RuntimeError(n+' source drift')
    if sha(reg['acceptance_path'])!=reg['acceptance_sha256'] or reg['acceptance_sha256']!='3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd': raise RuntimeError('acceptance pin mismatch')
    acceptance=j(reg['acceptance_path'])
    if acceptance.get('status')!='accepted_checkpoint324_replaces348_by_registered_fresh_confirmation' or acceptance.get('retained_update')!=324 or acceptance.get('checkpoint_sha256')!=reg['checkpoint_sha256'] or acceptance.get('source_integrity_receipt_sha256')!=reg['parent_receipt_sha256']: raise RuntimeError('accepted parent binding mismatch')
    if j(reg['vectors_path'])!=reg['vectors']: raise RuntimeError('vector content drift')
    if sha(reg['vectors_path'])!=reg['vectors_sha256']: raise RuntimeError('vector file drift')
    if sha(reg['checkpoint_path'])!=reg['checkpoint_sha256'] or reg['checkpoint_sha256']!=probe.PARENT: raise RuntimeError('checkpoint bytes pin mismatch')
    if sha(reg['parent_receipt_path'])!=reg['parent_receipt_sha256'] or reg['parent_receipt_sha256']!=probe.PARENT_RECEIPT: raise RuntimeError('parent receipt pin mismatch')
    rt=reg['runtime']
    if Path(sys.executable).absolute()!=Path(rt['python_path']).absolute() or sys.prefix!=rt['expected_venv_prefix'] or sys.version.split()[0]!=rt['python_version']: raise RuntimeError('interpreter invocation/prefix/version mismatch')
    cache=Path(rt['empty_cache_path'])
    if not cache.exists() or not cache.is_dir() or any(cache.iterdir()): raise RuntimeError('owned empty cache check failed')
    allowed={'worker.log','worker-heartbeat.json'}
    if Path(reg['output_dir']).exists() and any(p.name not in allowed for p in Path(reg['output_dir']).iterdir()): raise RuntimeError('output collision')
    if Path(reg['cancel_path']).exists(): raise RuntimeError('cancelled')
    st=j(reg['state_path'])
    if st.get('active_inference_diagnostic')!=reg['expected_lease']: raise RuntimeError('lease changed')
    if any(st.get(k) not in (None,False) for k in ('active_long_campaign','active_long','active_inference')): raise RuntimeError('conflicting lease')
    m=j(reg['one_shot_marker'])
    if m.get('run_id')!=reg['run_id'] or m.get('registration_sha256')!=regsha: raise RuntimeError('marker changed')

def main():
    global probe
    ap=argparse.ArgumentParser(); ap.add_argument('--registration',required=True); ap.add_argument('--registration-sha256',required=True); ap.add_argument('--heartbeat',required=True); ap.add_argument('--deadline',type=float,required=True); a=ap.parse_args()
    rp=Path(a.registration); reg=j(rp)
    if sha(rp)!=a.registration_sha256: raise RuntimeError('registration hash drift')
    probe_path=Path(reg['source']['probe_path']); raw_probe=probe_path.read_bytes()
    if hashlib.sha256(raw_probe).hexdigest()!=reg['source']['probe_sha256']: raise RuntimeError('probe source buffer pin mismatch')
    import importlib.util
    spec=importlib.util.spec_from_file_location('_verified_probe',probe_path); probe=importlib.util.module_from_spec(spec); exec(compile(raw_probe,str(probe_path),'exec'),probe.__dict__)
    check(rp,a.registration_sha256,reg,Path(__file__))
    # Test injection exists only for explicit isolated synthetic registration.
    test=reg.get('synthetic_test_dependencies')
    if test:
        if reg.get('status')!='synthetic_test_only' or reg.get('authority')!='synthetic_test_only' or os.environ.get('RNG_PROBE_SYNTHETIC_TEST')!='1': raise RuntimeError('synthetic dependency gate rejected')
        import importlib.util
        def load(name,path):
            raw=Path(path).read_bytes(); expected=test['runtime_sha256'] if name=='_fake_runtime' else reg['source']['fingerprint_sha256']
            if hashlib.sha256(raw).hexdigest()!=expected: raise RuntimeError('synthetic source buffer pin mismatch')
            spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); exec(compile(raw,str(path),'exec'),mod.__dict__); return mod
        api=load('_fake_runtime',test['runtime_path']); fpmod=load('_fake_fingerprint',reg['source']['fingerprint_path'])
        torch_api=api.Torch(); numpy_version='2.5.4'; torch_version='2.14.1'; python_version='3.12.15'; backend=True
        memory_sample=api.memory_sample
    else:
        rt=reg['runtime'];
        if Path(sys.executable).absolute()!=Path(rt['python_path']).absolute() or sys.version.split()[0]!=rt['python_version']: raise RuntimeError('interpreter pin mismatch')
        cache=Path(rt['empty_cache_path'])
        if not cache.is_dir() or any(cache.iterdir()): raise RuntimeError('owned empty cache preflight failed')
        import numpy,torch
        if numpy.__version__!='2.5.4' or torch.__version__!='2.14.1' or not torch.backends.mps.is_available(): raise RuntimeError('pinned runtime/MPS preflight failed')
        torch_api=torch; numpy_version=numpy.__version__; torch_version=torch.__version__; python_version=sys.version.split()[0]; backend=True
        import resource
        def memory_sample():
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss=int(peak if sys.platform=='darwin' else peak*1024)
            return rss,int(torch.mps.driver_allocated_memory())
        fpmod=None
    stop=threading.Event(); errors=[]; lock=threading.Lock()
    def sample_and_publish():
        rss,mps=memory_sample()
        if type(rss)is not int or type(mps)is not int or rss<0 or mps<0 or rss>reg['limits']['RSS_bytes'] or mps>reg['limits']['MPS_driver_bytes']: raise RuntimeError('heartbeat resource cap exceeded')
        rec={'run_id':reg['run_id'],'registration_sha256':a.registration_sha256,'pid':os.getpid(),'timestamp_ns':time.time_ns(),'sequence':time.monotonic_ns(),'rss_bytes':rss,'mps_driver_bytes':mps}
        tmp=Path(a.heartbeat).with_name(Path(a.heartbeat).name+'.tmp.'+str(os.getpid())); fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f: json.dump(rec,f); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,a.heartbeat)
    def heartbeat():
        while not stop.is_set():
            try:
                sample_and_publish()
            except BaseException as e:
                with lock: errors.append(e)
                stop.set(); return
            stop.wait(.2)
    t=threading.Thread(target=heartbeat,daemon=True); t.start()
    try:
        check(rp,a.registration_sha256,reg,Path(__file__))
        if time.monotonic()>=a.deadline: raise TimeoutError('worker deadline elapsed')
        fingerprint=(lambda b: __import__('hashlib').sha256(bytes(b)).hexdigest()) if test else None
        if test:
            fingerprint=lambda b: hashlib.sha256(bytes(b)).hexdigest()
        else:
            raw=Path(reg['source']['fingerprint_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=reg['source']['fingerprint_sha256'] or reg['source']['fingerprint_sha256']!='6ef9cf3f08fe800f54230801a921a2f5c82e47e5013ef3087ead6499d2533d61': raise RuntimeError('fingerprint source buffer pin mismatch')
            mod=type(sys)('_verified_fp'); exec(compile(raw,reg['source']['fingerprint_path'],'exec'),mod.__dict__); fingerprint=mod.fingerprint
        captured=probe.capture_references(vectors=reg['vectors'],study_id=reg['study_id'],torch_api=torch_api,numpy_version=numpy_version,python_version=python_version,torch_version=torch_version,backend_available=backend,fingerprint=fingerprint)
        check(rp,a.registration_sha256,reg,Path(__file__))
        stop.set(); t.join(1)
        if t.is_alive(): raise RuntimeError('heartbeat thread did not stop')
        if errors: raise RuntimeError('heartbeat thread failed') from errors[0]
        if time.monotonic()>=a.deadline: raise TimeoutError('worker deadline elapsed')
        check(rp,a.registration_sha256,reg,Path(__file__))
        # Force a fresh RSS/MPS sample after capture and after heartbeat shutdown.
        sample_and_publish()
        latest=j(a.heartbeat)
        if (time.time_ns()-latest.get('timestamp_ns',0))/1e9>reg['limits']['heartbeat_stale_seconds']: raise RuntimeError('heartbeat stale before publish')
        if latest.get('mps_driver_bytes',-1)>reg['limits']['MPS_driver_bytes'] or latest.get('rss_bytes',-1)>reg['limits']['RSS_bytes']: raise RuntimeError('resource cap before publish')
        check(rp,a.registration_sha256,reg,Path(__file__))
        if time.monotonic()>=a.deadline: raise TimeoutError('worker deadline elapsed')
        probe.atomic_publish(reg['output_dir'],captured)
    finally:
        stop.set(); t.join(1)
if __name__=='__main__': main()
