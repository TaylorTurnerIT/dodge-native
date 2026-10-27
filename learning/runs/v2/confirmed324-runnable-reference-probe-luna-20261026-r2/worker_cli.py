"""One-shot RNG reference worker CLI. Production imports occur after byte/path gates."""
import argparse,hashlib,json,os,sys,threading,time
from pathlib import Path
import probe

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def j(path): return json.loads(Path(path).read_text())
def check(regpath,regsha,reg,workerpath):
    if sha(regpath)!=regsha: raise RuntimeError('registration hash drift')
    if reg.get('schema')!='d2_layerb_rng_reference_probe_registration_v1': raise RuntimeError('registration schema mismatch')
    if reg.get('_external_registration_sha256') not in (None,regsha): raise RuntimeError('registration external hash mismatch')
    for n in ('worker','supervisor','probe','fingerprint'):
        p=reg['source'][n+'_path']; h=reg['source'][n+'_sha256']
        if Path(p).resolve()!=Path({'worker':workerpath,'supervisor':Path(__file__).with_name('supervisor_cli.py'),'probe':Path(__file__).with_name('probe.py'),'fingerprint':reg['source']['fingerprint_path']}[n]).resolve() or sha(p)!=h: raise RuntimeError(n+' source drift')
    if j(reg['vectors_path'])!=reg['vectors']: raise RuntimeError('vector content drift')
    if sha(reg['vectors_path'])!=reg['vectors_sha256']: raise RuntimeError('vector file drift')
    if sha(reg['checkpoint_path'])!=reg['checkpoint_sha256'] or reg['checkpoint_sha256']!=probe.PARENT: raise RuntimeError('checkpoint bytes pin mismatch')
    if sha(reg['parent_receipt_path'])!=reg['parent_receipt_sha256'] or reg['parent_receipt_sha256']!=probe.PARENT_RECEIPT: raise RuntimeError('parent receipt pin mismatch')
    allowed={'worker.log','worker-heartbeat.json'}
    if Path(reg['output_dir']).exists() and any(p.name not in allowed for p in Path(reg['output_dir']).iterdir()): raise RuntimeError('output collision')
    if Path(reg['cancel_path']).exists(): raise RuntimeError('cancelled')
    st=j(reg['state_path'])
    if st.get('active_inference_diagnostic')!=reg['expected_lease']: raise RuntimeError('lease changed')
    if any(st.get(k) not in (None,False) for k in ('active_long_campaign','active_long','active_inference')): raise RuntimeError('conflicting lease')
    m=j(reg['one_shot_marker'])
    if m.get('run_id')!=reg['run_id'] or m.get('registration_sha256')!=regsha: raise RuntimeError('marker changed')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--registration',required=True); ap.add_argument('--registration-sha256',required=True); ap.add_argument('--heartbeat',required=True); ap.add_argument('--deadline',type=float,required=True); a=ap.parse_args()
    rp=Path(a.registration); reg=j(rp); check(rp,a.registration_sha256,reg,Path(__file__))
    # Test injection exists only for explicit isolated synthetic registration.
    test=reg.get('synthetic_test_dependencies')
    if test:
        if reg.get('authority')!='synthetic_test_only' or os.environ.get('RNG_PROBE_SYNTHETIC_TEST')!='1': raise RuntimeError('synthetic dependency gate rejected')
        import importlib.util
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
        api=load('_fake_runtime',test['runtime_path']); fpmod=load('_fake_fingerprint',reg['source']['fingerprint_path'])
        torch_api=api.Torch(); numpy_version='2.5.4'; torch_version='2.14.1'; python_version='3.12.15'; backend=True
        memory_sample=api.memory_sample
    else:
        rt=reg['runtime'];
        if Path(sys.executable).resolve()!=Path(rt['python_path']).resolve() or sys.version.split()[0]!=rt['python_version']: raise RuntimeError('interpreter pin mismatch')
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
    def heartbeat():
        while not stop.is_set():
            try:
                rss,mps=memory_sample()
                if type(rss)is not int or type(mps)is not int or rss<0 or mps<0 or rss>reg['limits']['RSS_bytes'] or mps>reg['limits']['MPS_driver_bytes']: raise RuntimeError('heartbeat resource cap exceeded')
                rec={'run_id':reg['run_id'],'registration_sha256':a.registration_sha256,'pid':os.getpid(),'timestamp_ns':time.time_ns(),'sequence':time.monotonic_ns(),'rss_bytes':rss,'mps_driver_bytes':mps}
                tmp=Path(a.heartbeat).with_name(Path(a.heartbeat).name+'.tmp.'+str(os.getpid())); fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'w') as f: json.dump(rec,f); f.flush(); os.fsync(f.fileno())
                os.replace(tmp,a.heartbeat)
            except BaseException as e:
                with lock: errors.append(e)
                stop.set(); return
            stop.wait(.2)
    t=threading.Thread(target=heartbeat,daemon=True); t.start()
    try:
        check(rp,a.registration_sha256,reg,Path(__file__))
        if time.monotonic()>=a.deadline: raise TimeoutError('worker deadline elapsed')
        fingerprint=(lambda b: __import__('hashlib').sha256(bytes(b)).hexdigest()) if test else None
        if test: fingerprint=lambda b: hashlib.sha256(bytes(b)).hexdigest()
        else:
            raw=Path(reg['source']['fingerprint_path']).read_bytes(); mod=type(sys)('_verified_fp'); exec(compile(raw,reg['source']['fingerprint_path'],'exec'),mod.__dict__); fingerprint=mod.fingerprint
        captured=probe.capture_references(vectors=reg['vectors'],study_id=reg['study_id'],torch_api=torch_api,numpy_version=numpy_version,python_version=python_version,torch_version=torch_version,backend_available=backend,fingerprint=fingerprint)
        check(rp,a.registration_sha256,reg,Path(__file__))
        stop.set(); t.join(1)
        if t.is_alive(): raise RuntimeError('heartbeat thread did not stop')
        if errors: raise RuntimeError('heartbeat thread failed') from errors[0]
        if time.monotonic()>=a.deadline: raise TimeoutError('worker deadline elapsed')
        check(rp,a.registration_sha256,reg,Path(__file__))
        latest=j(a.heartbeat)
        if (time.time_ns()-latest.get('timestamp_ns',0))/1e9>reg['limits']['heartbeat_stale_seconds']: raise RuntimeError('heartbeat stale before publish')
        if latest.get('mps_driver_bytes',-1)>reg['limits']['MPS_driver_bytes'] or latest.get('rss_bytes',-1)>reg['limits']['RSS_bytes']: raise RuntimeError('resource cap before publish')
        probe.atomic_publish(reg['output_dir'],captured)
    finally:
        stop.set(); t.join(1)
if __name__=='__main__': main()
