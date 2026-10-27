import hashlib,json,pathlib,sys
ROOT=pathlib.Path.cwd();SOURCE=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2';OWN=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-parent-assembly-20261026-r2'
sys.path.insert(0,str(SOURCE))
regpath=ROOT/'learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json'
assert hashlib.sha256(regpath.read_bytes()).hexdigest()=='0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e'
reg=json.loads(regpath.read_text());worker_cache=pathlib.Path(reg['import_policy']['pycache_prefix']);assert worker_cache==ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache'
assert worker_cache.is_dir() and not any(worker_cache.iterdir())
import bootstrap_readiness,wrapper
binding_sha=json.loads((OWN/'binding-receipt.json').read_text())['binding_sha256']
record=bootstrap_readiness.bootstrap(expected_binding_sha256=binding_sha)
auditor=wrapper.load_auditor();runner,loaded,config=auditor.load_frozen(expected_binding_sha256=binding_sha)
assert loaded==reg
strict=wrapper.make_strict_import_runtime(auditor.import_runtime,reg);strict(reg)
origins=wrapper.check_loaded_dodge(reg,pathlib.Path(reg['runtime_root']).resolve(),reg['runtime_continuity']['member_sha256'])
assert not any(worker_cache.iterdir()) and not any(wrapper.PYCACHE_PREFIX.iterdir())
record.update(worker_prefix_empty_pre_post=True,auditor_prefix_empty_pre_post=True,strict_Dodge_origins=origins,MPS_used=False,environment_constructed=False,actual_candidate_audit=False)
(OWN/'bootstrap-receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
