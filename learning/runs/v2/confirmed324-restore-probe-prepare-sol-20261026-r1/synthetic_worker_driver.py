"""Test-only instrumentation of the real worker CLI. Never used by registrations."""
import builtins
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','numpy','dodge_rl'}: raise RuntimeError('runtime import forbidden by synthetic driver: '+fullname)
sys.meta_path.insert(0,NoRuntime())
import probe
import worker_cli
from test_restore_probe import ProbeControls
mode=sys.argv[1]; root=Path(sys.argv[2]); root.mkdir(exist_ok=True)
f=ProbeControls(); f.setUp(); f.temp._finalizer.detach()  # retain every synthetic input/receipt
reg=f.reg; out=root/'out'; out.mkdir()
reg['output_dir']=str(out); reg['one_shot_marker']=str(root/'outer.claimed')
reg['cancel_path']=str(root/'CANCEL'); reg['state_path']=str(root/'state.json')
rp=root/'registration.json'; rp.write_text(json.dumps(reg)); rsha=probe.sha(rp)
f.adapter.torch.mps.driver_allocated_memory=lambda:0
if mode=='mutating-restore': f.mutate=True
if mode=='cleanup-failure':
    def broken_sync(): raise RuntimeError('synthetic sync failure')
    f.adapter.torch.mps.synchronize=broken_sync
if mode=='signal-bootstrap':
    def blocked_bootstrap():
        (root/'ready').write_text('stdlib worker ready')
        time.sleep(30)
    f.adapter.bootstrap=blocked_bootstrap
cls=f.modules['runtime_adapter'].RuntimeAdapter

def fake_init(self,reg,context):
    self.__dict__.update(f.adapter.__dict__)
    if mode=='constructor-failure': raise RuntimeError('synthetic constructor failure after torch assignment')
cls.__init__=fake_init
f.t.EXPECTED_PARENT=f.expected
f.t._sha256_file=lambda path:probe.PARENT_RECEIPT if Path(path)==f.receipt else probe.PARENT
real_exec=builtins.exec

def instrument(code,globals=None,locals=None,**kwargs):
    result=real_exec(code,globals,locals,**kwargs)
    if getattr(code,'co_filename',None)==str(HERE/'probe.py') and globals.get('__name__')=='_verified_restore_probe':
        # Explicit test-only bypass of parent gates. Registration gate controls run
        # separately against unmodified production functions with real frozen pins.
        globals['preflight']=lambda *args,**kw:None
        globals['verify_immutable']=lambda reg:(f.modules,{})
        globals['adapter_subset']=lambda reg,context:{}
        globals['EXPECTED']=f.expected
        globals['runtime_identity']=lambda *args:__import__('synthetic_payload').runtime_fixture(reg)
    return result
builtins.exec=instrument
sys.argv=[str(HERE/'worker_cli.py'),'--registration',str(rp),'--registration-sha256',rsha,'--heartbeat',str(out/'worker-heartbeat.json'),'--deadline',str(time.monotonic()+12)]
try: worker_cli.main()
finally:
    modules=[n for n in sys.modules if n.split('.')[0] in {'torch','numpy','dodge_rl'}]
    (root/'driver-scope.json').write_text(json.dumps(dict(mode=mode,real_runtime_modules=modules,test_only_instrumentation=True,real_parent_gates_bypassed=True)))
