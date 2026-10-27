from pathlib import Path
import hashlib,json,datetime,subprocess,sys
O=Path(__file__).resolve().parent;H=O.parent/'postovernight-long-D2-guard-prepare-r1';R=Path.cwd()
def sha(p):
 d=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):d.update(b)
 return d.hexdigest()
inv=json.loads((H/'artifact-inventory-final.json').read_text());errors=[];writable=[]
for n,d in inv['files'].items():
 p=H/n
 if sha(p)!=d['sha256'] or p.stat().st_size!=d['bytes']:errors.append(n)
 if p.stat().st_mode&0o222:writable.append(n)
assert not errors and not writable
v=json.loads((O/'verification.json').read_text());assert all(sha(H/n)==d for n,d in v['sha256'].items())
helpers={n:sha(H/n)==sha(H.parent/'postovernight-long-D2-prepare-r4'/n) for n in ['lifecycle.py','processes.py']};assert all(helpers.values())
m=json.loads((H/'attempts/matrix-01-cases/summary.json').read_text());missing=[];injected=0
for r in m['results']:
 p=Path(r['argv'][-1]);opts=json.loads((p/'options.json').read_text())
 if opts.get('phase'):
  injected+=1
  if not r['injection_reached']:missing.append(p.name)
assert injected==60 and not missing
post={'schema':'readonly_review_preservation_postcheck_v1','verified_artifact_entries':len(inv['files']),'changed_entries':errors,'writable_entries':writable,'candidate_supplied_hashes_unchanged':True,'helpers_byte_equal_to_R4':helpers,'registered_matrix_injection_phases':injected,'missed_registered_injections':missing,'no_phase_cases':2,'candidate_accepted_for_training':False,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(O/'preservation-postcheck.json').write_text(json.dumps(post,indent=2)+'\n')
# Exact syntax checks required for evidence JSON; no project imports or tests.
rows=[]
for p in sorted(O.rglob('*.json')):
 process=subprocess.run([sys.executable,'-B','-m','json.tool',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
 rows.append({'path':str(p.relative_to(O)),'argv':[sys.executable,'-B','-m','json.tool',str(p)],'raw_exit':process.returncode,'stderr':process.stderr})
assert all(r['raw_exit']==0 for r in rows)
(O/'json-validation.json').write_text(json.dumps({'validated':len(rows),'success':True,'commands':rows},indent=2)+'\n')
print(json.dumps({'candidate_artifact_entries_rechecked':len(inv['files']),'changed':len(errors),'writable':len(writable),'json_files_validated':len(rows),'registered_injections_reached':injected}))
