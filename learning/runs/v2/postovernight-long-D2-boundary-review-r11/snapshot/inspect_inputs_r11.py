"""Preparation input reads and provenance only; no candidate validation launch."""
from pathlib import Path
import hashlib,json,datetime
H=Path(__file__).resolve().parent;ROOT=H.parents[3];BASE=H.parent
files=[ROOT/'docs/implementation-plan-v2.md',ROOT/'docs/SPEC_PRIVILEGED_VIT_RL.md',ROOT/'learning/runs/v2-orchestration/state.json']
for name in ('postovernight-long-D2-boundary-review-r10','postovernight-long-D2-escalation-reap-design-sonnet-r1'):
 files.extend(p for p in (BASE/name).iterdir() if p.is_file() and p.suffix in ('.py','.json','.md','.diff','.log'))
for name in ('postovernight-long-D2-boundary-repair-r10-task.md','postovernight-long-D2-boundary-repair-r7-task.md','postovernight-long-D2-boundary-repair-r4-task.md','postovernight-long-D2-boundary-review-r10-parent-reconciliation.json','postovernight-long-D2-escalation-reap-sonnet-r1-parent-reconciliation.json','postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json'):
 files.append(ROOT/'learning/runs/v2-orchestration'/name)
files.extend(p for p in (BASE/'postovernight-long-D2-boundary-prepare-r10').glob('*.py'))
files.extend(BASE/'postovernight-long-D2-boundary-prepare-r10'/n for n in ('parent-result-r10.json','implementation-result.json','PARENT-NEXT.md','parent-frozen-pins.json','protocol-r7-proposal.json','candidate.diff'))
manifest={};parsed={}
for p in sorted(set(files)):
 raw=p.read_bytes();text=raw.decode();manifest[str(p.relative_to(ROOT))]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),full_read=True)
 if p.suffix=='.json':parsed[str(p.relative_to(ROOT))]=json.loads(text)
state=parsed['learning/runs/v2-orchestration/state.json']
# Full state is parsed; expose every current boundary/escalation/IPC-related record.
relevant={}
def walk(value,path=''):
 if isinstance(value,dict):
  for key,item in value.items():
   name=path+'/'+key
   if any(word in key.lower() for word in ('boundary','escalation','ipc','lease')):relevant[name]=item
   else:walk(item,name)
 elif isinstance(value,list):
  for i,item in enumerate(value):walk(item,path+'/'+str(i))
walk(state)
(H/'read-input-manifest.json').write_text(json.dumps(dict(schema='r11_read_inputs_v1',files=manifest,state_mutable_context_only=True,read_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
(H/'state-context-relevant.json').write_text(json.dumps(relevant,indent=2)+'\n')
print(json.dumps(dict(full_files_read=len(manifest),state_top_level_keys=list(state),relevant_state_paths=list(relevant),historical_r10_status=parsed['learning/runs/v2/postovernight-long-D2-boundary-prepare-r10/parent-result-r10.json']['status']),indent=2))
