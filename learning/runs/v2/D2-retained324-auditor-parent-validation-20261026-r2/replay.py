import hashlib,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path.cwd()
OUT=pathlib.Path(__file__).resolve().parent
SOURCE=ROOT/'learning/runs/v2/D2-retained324-all-candidate-auditor-luna-20261026-r2'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((SOURCE/'output-manifest.json').read_text())
assert digest(SOURCE/'output-manifest.json')=='7dddb60e2f78c1f50ce0f0012a4625cad02012ee2490a4d3351e706911cf865d'
for name,expected in manifest['outputs'].items():
    assert digest(SOURCE/name)==expected,name
reg=json.loads((ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/registration.json').read_text())
state_path=ROOT/'learning/runs/v2-orchestration/state.json'
lease_before=json.loads(state_path.read_text())['active_long_campaign']
assert lease_before==reg['expected_lease']
env=os.environ.copy();env.pop('PYTHONPATH',None)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(SOURCE/'empty-pycache'),OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
python=str(ROOT/'python/.venv/bin/python')
code='import sys,unittest;sys.path.insert(0,'+repr(str(SOURCE))+');suite=unittest.defaultTestLoader.loadTestsFromNames(["test_audit_candidates","test_source_contract"]);result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())'
with (OUT/'controls.log').open('x') as stream:
    result=subprocess.run([python,'-B','-c',code],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
assert result.returncode==0,'CPU controls failed'
bootstrap=(SOURCE/'bootstrap.py').read_text().replace("pathlib.Path(__file__).with_name('bootstrap.json')",repr(str(OUT/'bootstrap.json')))
# Wrap absolute output string as a Path while preserving every bootstrap check.
bootstrap=bootstrap.replace(repr(str(OUT/'bootstrap.json'))+'.write_text','pathlib.Path('+repr(str(OUT/'bootstrap.json'))+').write_text')
(OUT/'bootstrap.py').write_text(bootstrap)
with (OUT/'bootstrap.log').open('x') as stream:
    result=subprocess.run([python,'-B',str(OUT/'bootstrap.py')],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
assert result.returncode==0,'Startup bootstrap failed'
assert json.loads(state_path.read_text())['active_long_campaign']==lease_before
assert not any((SOURCE/'empty-pycache').iterdir())
for name,expected in manifest['outputs'].items():assert digest(SOURCE/name)==expected,name
receipt={'status':'passed','CPU_controls':12,'child_output_hashes_verified':len(manifest['outputs']),'bootstrap':json.loads((OUT/'bootstrap.json').read_text()),'lease_unchanged':True,'current_outputs_read':False,'full_audit_ran':False,'MPS_used':False,'logs':{name:digest(OUT/name) for name in ('controls.log','bootstrap.log','bootstrap.py','bootstrap.json')}}
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
