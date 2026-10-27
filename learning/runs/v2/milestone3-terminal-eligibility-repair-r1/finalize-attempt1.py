"""Finalize bounded repair evidence without modifying parent-owned state."""
from datetime import datetime, timezone
from pathlib import Path
import difflib,hashlib,json,shutil,subprocess,tarfile,xml.etree.ElementTree as ET
from dodge_rl.identity import source_inventory
root=Path.cwd();out=root/'learning/runs/v2/milestone3-terminal-eligibility-repair-r1'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,value):
 (out/name).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
before=json.loads((out/'owned-before-sha256.json').read_text())
owned=sorted(set(before)|{str(p) for p in Path('python/tests').glob('test_terminal_*.py')})
after={p:h(root/p) for p in owned}
for p in owned:
 target=out/'after'/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/p,target)
write('owned-after-sha256.json',after)
assert all(h(out/'before'/p)==digest for p,digest in before.items())
changed=[p for p in owned if before.get(p)!=after[p]]
allowed={'python/dodge_rl/train_teacher.py','python/dodge_rl/checkpoints.py','python/dodge_rl/supervision.py','python/tests/test_checkpoints.py','python/tests/test_teacher_runner.py','python/tests/test_runtime_repair.py','python/tests/test_terminal_eligibility.py','python/tests/test_terminal_runtime.py'}
assert set(changed)==allowed,changed
patch=''
for p in changed:
 original=(out/'before'/p).read_text().splitlines(True) if p in before else []
 patch+=''.join(difflib.unified_diff(original,(root/p).read_text().splitlines(True),fromfile='before/'+p if p in before else '/dev/null',tofile='after/'+p))
(out/'repair.patch').write_text(patch)
protected=json.loads((out/'protected-before.json').read_text());protected_after={p:h(root/p) for p in protected}
assert protected_after==protected
write('protected-after.json',protected_after)
pins=json.loads((out/'all73-before.json').read_text());old_after={p:h(root/p) for p in pins}
write('all73-after.json',old_after)
assert {p for p in pins if pins[p]!=old_after[p]}==allowed-{'python/tests/test_terminal_eligibility.py','python/tests/test_terminal_runtime.py'}
source=source_inventory();write('source-manifest.json',source)
frozen=root/'learning/.cache/v2-m3-runtime-review-r2'
frozen_after={str(p.relative_to(frozen)):h(p) for p in sorted(frozen.rglob('*')) if p.is_file()}
assert frozen_after==json.loads((out/'frozen-capsule-before.json').read_text())
write('frozen-capsule-after.json',frozen_after)
assert h(frozen/'manifest.json')=='a0d37ad518e30ef5acf7c38ec777503b03b3a79bd8f8cd44b84bb6949b70755d'
identity_path=frozen/'learning/runs/v2/milestone3-integration-r2/probe-frozen-identity.json'
assert h(identity_path)=='bc25a3c555673f9f32c01d6f1f08b8cc0df59a2657f5600ec47ee98047d2b8a2'
negative=[];tests=[]
for directory in sorted(out.iterdir()):
 receipt=directory/'command-result.json'
 if not receipt.is_file():continue
 command=json.loads(receipt.read_text());assert command['source_unchanged_during_test']
 suites=ET.parse(directory/'junit.xml').getroot();cases=list(suites.iter('testcase'))
 failures=[case for case in cases if case.find('failure') is not None]
 errors=[case for case in cases if case.find('error') is not None]
 row={'label':directory.name,'exit_status':command['exit_status'],'tests':len(cases),'failed':len(failures),'errors':len(errors),'passed':len(cases)-len(failures)-len(errors),'duration_seconds':command['duration_seconds'],'command_receipt':str(receipt.relative_to(out)),'log':str((directory/'stdout-stderr.log').relative_to(out)),'log_sha256':h(directory/'stdout-stderr.log'),'executed_source_manifest':str((directory/'executed-source.json').relative_to(out))}
 tests.append(row)
 if directory.name.startswith('frozen-r2'):
  assert not errors
  for case in failures:
   failure=case.find('failure');body=''.join(failure.itertext())
   assert failure.attrib['type'] in {'Failed','AssertionError'},failure.attrib
   assert 'TypeError:' not in body and 'AttributeError:' not in body and 'ImportError:' not in body
   negative.append({'run':directory.name,'case':case.attrib['name'],'type':failure.attrib['type'],'message':failure.attrib['message']})
write('negative-control-classification.json',{'behavioral_failures':negative,'missing_API_or_collection_errors_used_as_evidence':0,'expected_behavioral_failures':len(negative)})
with tarfile.open(out/'source-before-after.tar.gz','w:gz') as archive:
 for prefix in ('before','after'):
  archive.add(out/prefix,arcname=prefix)
state=json.loads((root/'learning/runs/v2-orchestration/state.json').read_text())
assert state['active_long_campaign'] is None
now=datetime.now(timezone.utc);started=datetime.fromisoformat('2026-10-24T10:45:36+00:00')
assert (now-started).total_seconds()<1200
result={
 'status':'bounded_terminal_eligibility_repair_synthetic_CPU_passed_pending_parent_freeze_and_review_r3',
 'started_at_utc':started.isoformat(),'finished_at_utc':now.isoformat(),'elapsed_seconds':(now-started).total_seconds(),'budget_seconds':1200,'deadline_utc':'2026-10-24T11:05:36Z','cutoff_utc':'2026-10-24T13:00:00Z',
 'changed_files':changed,'owned_after_sha256':{p:after[p] for p in changed},
 'source_manifest_sha256':h(out/'source-manifest.json'),'source_manifest_entries':len(source),
 'protected_inputs_unchanged':len(protected),'original_source_pins':len(pins),'original_source_pins_changed_in_owned_scope':sum(pins[p]!=old_after[p] for p in pins),'original_source_pins_unchanged':sum(pins[p]==old_after[p] for p in pins),
 'frozen_capsule_files_unchanged':len(frozen_after),'frozen_capsule_manifest_sha256':h(frozen/'manifest.json'),'frozen_identity_sha256':h(identity_path),'before_archive_unchanged':True,
 'patch':{'path':'repair.patch','sha256':h(out/'repair.patch')},'source_archive':{'path':'source-before-after.tar.gz','sha256':h(out/'source-before-after.tar.gz')},
 'test_runs':tests,'final_test_run':'repaired-cpu-final2','frozen_r2_behavioral_failures':len(negative),'negative_control_missing_API_errors':0,
 'fixture_corrections':'fixture-corrections.json','recorder_prelaunch_failure':'repaired-cpu-attempt1/recorder-failure.json',
 'repairs':[
  'Required parent-pinned terminal run-result hash and parent-observed exact supervisor exit0. Check successful run/worker status, identity/config lease hashes, finite in-budget source phase time, exact checkpoint/certificate, and critical manifest entries.',
  'Transition requires terminal_anchor keyword, exact source run-end candidate, complete optimizer-update state, semantic checkpoint/run identity and registered-config equality; prior source/runtime/config/registered-phase/gate checks retained.',
  'Read actual parent lease; require parent_terminal_receipt for D1/D2/D3 and absent for fresh probe/pilot. Capture anchor and compare on every guard call. Supervisor validates before mkdir/Popen; Experiment validates before learner construction and again before restore; lineage records anchor.',
  'Supervisor and worker return nonzero for any recorded cancellation, including first signal deferred during finalization after passing receipts/manifest. Existing immutable receipts stay untouched and exact owned-group cleanup stays bounded.'
 ],
 'evidence_boundaries':[
  'Synthetic CPU tests only, including tiny learner/optimizer/RNG fixtures, mocked environments/processes and plain Python signal subprocesses. No gameplay campaign, probe, pilot or training executed.',
  'Test counts and behavioral controls do not qualify source, runtime performance, MPS, teacher competence or campaign authorization.',
  'No model/PPO/native/identity.py/dev_eval.py/docs/protocol/config-schema/parent-ledger mutation, build, install, provider retry, commit, publication or external review.',
  'One narrow helper wrote only the new terminal eligibility test file; root integrated and ran all tests.',
  'Same-phase resume remains disabled; prior runtime repairs remain in place.',
  'Parent must prepare next config and identity before publishing matching target lease, independently audit source terminal receipt and observed supervisor exit, freeze repaired inputs and obtain independent frozen review r3 before any campaign.',
  'Terminal artifact index provides consistency only; authority is parent-owned lease anchor. A passing certificate or even passed JSON receipt cannot replace parent-observed supervisor exit0.'
 ],
 'active_long_campaign_at_handoff':state['active_long_campaign'],'parent_owned_state_write':False,
}
write('result.json',result)
for label in ('result.json','owned-after-sha256.json','protected-after.json','negative-control-classification.json','source-manifest.json'):
 completed=subprocess.run([str(root/'python/.venv/bin/python'),'-B','-m','json.tool',str(out/label)],stdout=subprocess.DEVNULL,capture_output=False)
 assert completed.returncode==0
write('artifact-sha256.json',{str(p.relative_to(out)):h(p) for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'artifact-sha256.json'})
print(json.dumps({'result':str(out/'result.json'),'elapsed_seconds':result['elapsed_seconds'],'changed':changed,'protected':len(protected),'frozen_files':len(frozen_after),'final_tests':next(row for row in tests if row['label']=='repaired-cpu-final2'),'negative_behavioral_failures':len(negative),'artifact_manifest_sha256':h(out/'artifact-sha256.json')},indent=2))
