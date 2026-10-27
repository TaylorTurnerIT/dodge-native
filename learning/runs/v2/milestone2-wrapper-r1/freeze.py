"""Freeze exact source and retained evidence, without editing workspace inputs."""
import datetime
import difflib
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tarfile

ROOT=pathlib.Path(__file__).resolve().parents[4]
OUT=pathlib.Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')

inputs=json.loads((OUT/'input-manifest.json').read_text())
for path,expected in inputs['frozen_pins'].items():assert sha(ROOT/path)==expected,path
source_paths=['Cargo.toml','Cargo.lock','crates/dodge-rl-env/Cargo.toml']+[str(p.relative_to(ROOT)) for p in sorted((ROOT/'crates/dodge-rl-env').rglob('*.rs'))]
sources={p:sha(ROOT/p) for p in source_paths}
new_paths=[p for p in source_paths if p not in inputs['frozen_pins']]
assert len(new_paths)==11,(len(new_paths),new_paths)
commands=[json.loads(line) for line in (OUT/'commands.jsonl').read_text().splitlines()]
qualified={name:[r for r in commands if r['name']==name and r['exit_code']==0][-1] for name in ['test','fmt','clippy','replay']}
for name,r in qualified.items():
 assert not r['source_changed'],name
 for path,h in sources.items():assert r['source_sha256'][path]==h,(name,path)
assert len([r for r in commands if r['name']=='replay'])==1
assert len([r for r in commands if r['name']=='trajectory'])==1
original=(ROOT/'learning/runs/v2/milestone2-math-r1/fixtures.rs').read_bytes()
promoted=(ROOT/'crates/dodge-rl-env/tests/primitives.rs').read_bytes()
original_body=original[original.index(b'use geometry::{'):]
promoted_body=promoted[promoted.index(b'use geometry::{'):]
assert original_body==promoted_body
old_root=(OUT/'inputs/Cargo.toml').read_text();root=(ROOT/'Cargo.toml').read_text()
assert root==old_root.replace('    "crates/dodge-core",\n','    "crates/dodge-core",\n    "crates/dodge-rl-env",\n',1)
patch=[]
for path in new_paths:
 before=OUT/'inputs'/path
 old=before.read_text().splitlines(keepends=True) if before.exists() else []
 new=(ROOT/path).read_text().splitlines(keepends=True)
 patch.append(f'diff --git a/{path} b/{path}\n')
 if not before.exists():patch.append('new file mode 100644\n')
 patch.extend(difflib.unified_diff(old,new,fromfile='a/'+path if before.exists() else '/dev/null',tofile='b/'+path))
(OUT/'wrapper.patch').write_text(''.join(patch))
with tarfile.open(OUT/'source.tar.gz','w:gz') as tar:
 for path in source_paths:tar.add(ROOT/path,arcname=path,recursive=False)
with tarfile.open(OUT/'source.tar.gz','r:gz') as tar:
 for path,h in sources.items():assert hashlib.sha256(tar.extractfile(path).read()).hexdigest()==h
unit_results=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', (OUT/qualified['test']['log']).read_text())
assert unit_results==[('33','0','1'),('35','0','0'),('0','0','0')],unit_results
failed=[{'name':r['name'],'command':r['command'],'exit_code':r['exit_code'],'log':r['log'],'source_changed':r['source_changed']} for r in commands if r['exit_code']!=0]
assert len(failed)==3,failed
write('failure-ledger.json',{'failed_command_attempts':failed,'resolutions':{'check-01.log':'Unstable Option::map_or_default replaced with stable map_or. First dependency resolution also generated the authorized Cargo.lock additions; this is the only check with source_changed=true.','test-01.log':'Test support was initially unused before the release replay was added; replay now uses the exact frozen policy and observer seam.','clippy-01.log':'Factored a test-only RawObserver type alias; no lint suppression.','trajectory-checker-failure.log':'Native probe succeeded on its only execution. Result parser chose trajectory-01.log instead of actual trajectory-02.log; parse-only repair read the retained command receipt. No simulation rerun.'},'replay_attempts':1,'trajectory_native_attempts':1,'timeouts':0,'automatic_native_retries':0,'limit_increases':0})
write('source-manifest.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'source frozen for independent parent review; not parent acceptance','head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'new_or_changed_source_paths':new_paths,'source_sha256':sources,'frozen_input_pins_unchanged':inputs['frozen_pins'],'promoted_fixture_body_sha256':hashlib.sha256(promoted_body).hexdigest(),'original_fixture_body_sha256':hashlib.sha256(original_body).hexdigest(),'final_sources_match_successful_test_fmt_clippy_and_replay_receipts':True,'patch':'wrapper.patch','patch_sha256':sha(OUT/'wrapper.patch'),'source_archive':'source.tar.gz','source_archive_sha256':sha(OUT/'source.tar.gz')})
verification={'milestone':'Dodge v2 M2 pure Rust vectorized foundation, wrapper r1','status':'implemented and frozen; independent parent review required before PyO3','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'budget_seconds':3600,'started_approximately_utc':'2026-10-24T06:41:00Z','source_manifest':'source-manifest.json','source_manifest_sha256':sha(OUT/'source-manifest.json'),'source_patch':'wrapper.patch','source_archive':'source.tar.gz','checks':{name:{k:v for k,v in r.items() if k!='source_sha256'} for name,r in qualified.items()},'ordinary_crate_tests':{'unit_passed':33,'includes_frozen_M0_helper_tests':8,'promoted_math_passed':35,'total_passed':68,'replay_ignored_in_ordinary_run':1,'release_replay_test_passed_separately':1,'distinct_tests_executed_in_total':69},'baseline_replay':json.loads((OUT/'baseline-replay.json').read_text()),'thread_chunk_supplemental':json.loads((OUT/'trajectory.json').read_text()),'frozen_core_hashes_checked':7,'math_policy_and_promoted_fixture_unchanged':True,'failures':'failure-ledger.json','core_86_test_receipt':'Prior accepted core-only receipt; not rerun or counted here. Workspace all-target/all-feature Clippy compiles current core; wrapper replay separately exercises the current native paths.','production_snapshots_or_FullState':False,'Python_binding':False,'NumPy_owned_array_checks':'future binding task','100000_step_memory_check':'future binding task; no memory or zero-leak claim','throughput_campaign':'not run','snapshot_recovery_curriculum':'not implemented','models_student_PPO_training':'not implemented','external_Pemsa_runtime':'unrun','provider_retry_nested_agents_commits_PRs_deployments_external_messages':False,'limitations':['Conservative admission is not a general pixel-observability proof.','Slab and charge estimates do not predict growth/acceleration or later gameplay exactly.','Thirty M0 replay episodes all died; unit fixtures separately cover alive truncation and death/cap precedence.','Replay observed 22 catalog IDs, not all 39 entries.','Owned Rust buffers do not establish Python lifetime/GIL/NumPy behavior or memory stability.','Independent parent source review is pending.']}
write('verification.json',verification)
if (OUT/'__pycache__').exists():shutil.rmtree(OUT/'__pycache__')
subprocess.run(['git','status','--short'],cwd=ROOT,stdout=(OUT/'git-status-final.log').open('w'),check=True)
print(json.dumps({'source_files':len(sources),'changed_source_files':len(new_paths),'source_manifest_sha256':sha(OUT/'source-manifest.json'),'source_archive_sha256':sha(OUT/'source.tar.gz'),'patch_sha256':sha(OUT/'wrapper.patch'),'normal_crate_tests_passed':68,'release_replay_passed':True,'frozen_pins_unchanged':len(inputs['frozen_pins'])},indent=2))
