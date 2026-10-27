import os,json,hashlib,re,glob
ROOT='learning/runs/v2'; OUT=ROOT+'/expanded-evaluation-seed-exposure-audit-luna-20261026-r1'
PROPOSAL=ROOT+'/expanded-evaluation-registration-proposal-parent-20261026-r2/proposal.json'
# Closed record candidates; omit fixture/attempt copies and all B/E outcome directories.
files=[]
for base,dirs,names in os.walk(ROOT):
    rel=os.path.relpath(base,ROOT)
    dirs[:]=[d for d in dirs if d not in ('.git','__pycache__')]
    if re.search(r'(^|/)(B1000|E1000)(-|/|$)',rel,re.I): dirs[:]=[]; continue
    for n in names:
        p=os.path.join(base,n); rp=os.path.relpath(p,ROOT)
        if '/attempts/' in '/'+rp or '/fixtures/' in '/'+rp: continue
        if n.endswith(('.json','.jsonl')) and (n.endswith('.jsonl') or 'episode' in n or 'seed' in n or 'journal' in n): files.append(p)
# Explicit canonical source run output logs, including six candidate ancestry branches.
files += glob.glob(ROOT+'/D2-*/training-episodes.jsonl')
files=sorted(set(files))
p=json.load(open(PROPOSAL)); cohorts={k:set(range(int(v['range_inclusive'][0]),int(v['range_inclusive'][1])+1)) for k,v in p['cohorts'].items()}
# Parse numeric values only where field names identify seeds. Record evaluations and training separately.
hits={k:[] for k in cohorts}; source_stats=[]; eval_rows=0; train_rows=0; seedvals=set(); parse_errors=[]
def walk(x,path='',kind=''):
    global eval_rows,train_rows
    if isinstance(x,dict):
        seedobj=x.get('seed')
        if isinstance(seedobj,int):
            v=seedobj; ev=('development' in kind or 'eval' in kind)
            seedvals.add(v)
            if ev: eval_rows+=1
            else: train_rows+=1
            for c,s in cohorts.items():
                if v in s: hits[c].append({'path':path+'/seed','seed':v,'evaluation':ev,'episode':x.get('episode_index'),'kind':x.get('kind')})
        if isinstance(seedobj,dict):
            v=seedobj.get('actual_seed',seedobj.get('seed'))
            ev=seedobj.get('evaluation') is True or 'development' in kind or 'eval' in kind
            if isinstance(v,int):
                seedvals.add(v)
                if ev: eval_rows+=1
                else: train_rows+=1
                for c,s in cohorts.items():
                    if v in s: hits[c].append({'path':path,'seed':v,'evaluation':ev,'episode':seedobj.get('episode'),'kind':x.get('kind')})
        for k,v in x.items():
            if k in ('actual_seed','environment_seed','master_seed','seed_id') and isinstance(v,int):
                seedvals.add(v)
                for c,s in cohorts.items():
                    if v in s: hits[c].append({'path':path+'/'+k,'seed':v,'evaluation':('development' in kind or 'eval' in kind),'kind':x.get('kind')})
            walk(v,path+'/'+str(k),kind)
    elif isinstance(x,list):
        for i,v in enumerate(x): walk(v,path+'/'+str(i),kind)
for f in files:
    b=open(f,'rb').read(); sha=hashlib.sha256(b).hexdigest(); count=0
    try:
        if f.endswith('.jsonl'):
            for ln,line in enumerate(b.splitlines(),1):
                if not line.strip(): continue
                try: d=json.loads(line)
                except Exception as e: parse_errors.append({'path':f,'line':ln,'error':str(e)[:120]}); continue
                walk(d,f+':'+str(ln),os.path.basename(f)); count+=1
        else:
            d=json.loads(b); walk(d,f,os.path.basename(f)); count=1
    except Exception as e: parse_errors.append({'path':f,'error':str(e)[:120]})
    source_stats.append({'path':f,'sha256':sha,'bytes':len(b),'records':count})
# hashes of proposal, manifests, six receipt/audit refs
refs=[PROPOSAL]+[v['path'] for v in p['cohorts'].values()]+[c.get('source_receipt_path',c.get('source_audit_path')) for c in p['candidates']]
ref_hashes=[]
for f in refs:
 try:
  b=open(f,'rb').read(); ref_hashes.append({'path':f,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
 except Exception as e: ref_hashes.append({'path':f,'error':str(e)})

for c in hits:
    uniq={(h['path'],h['seed']):h for h in hits[c]}; hits[c]=list(uniq.values())
res={'schema':'seed_exposure_audit_v1','proposal_path':PROPOSAL,'proposal_sha256':hashlib.sha256(open(PROPOSAL,'rb').read()).hexdigest(),'cohorts':{k:{'size':len(s),'range':[min(s),max(s)],'collision_count':len(hits[k]),'collisions':hits[k]} for k,s in cohorts.items()},'records_scanned':sum(x['records'] for x in source_stats),'source_file_count':len(source_stats),'training_seed_records':train_rows,'evaluation_seed_records':eval_rows,'distinct_seed_values':len(seedvals),'source_hashes':source_stats,'reference_hashes':ref_hashes,'parse_errors':parse_errors,'limits':['Coverage is limited to present parseable JSON/JSONL episode, seed, and journal records under learning/runs/v2; missing or unrecorded construction/use cannot be ruled out.','No checkpoint binary read or deserialization.','B1000/E1000 outcome paths excluded.','No reservation registry/config union audit performed.','Parent receipt episode-index arrays were not reconciled against all episode rows in this pass.']}
json.dump(res,open(OUT+'/audit.json','w'),indent=2,sort_keys=True); open(OUT+'/audit.json','a').write('\n')
with open(OUT+'/report.md','w') as f:
 f.write('# Historical seed exposure audit\n\n')
 f.write('Read-only scan. Proposal ranges unchanged; no launch, gate, lease, reservation, or registry mutation.\n\n')
 for k,v in res['cohorts'].items(): f.write(f"- {k}: {'PASS logged subset' if not v['collision_count'] else 'FAIL collision'}; {v['size']} proposed seeds; {v['collision_count']} logged intersections.\n")
 f.write(f"\nScanned {res['source_file_count']} files ({res['records_scanned']} parsed records); {train_rows} training-seed records, {eval_rows} evaluation-seed records, {len(seedvals)} distinct numeric seed values.\n\n")
 f.write('## Proof limit\n\nCollision-free means only no intersection in covered, parseable logs. It does not prove complete historical nonuse. Parent next-episode indices and accepted receipt identities/counters remain unreconciled to every logged episode here. Missing or unrecorded construction/use blocks a complete exclusion claim. Future exclusion union/config/reservation review remains required; this audit does not install it.\n\n')
 f.write('## Collision details\n\n')
 for k,v in res['cohorts'].items():
  f.write(f"### {k}\n\n")
  for h in v['collisions']: f.write(f"- `{h['seed']:#x}` at `{h['path']}` ({'evaluation' if h['evaluation'] else 'training'}).\n")
  if not v['collisions']: f.write('None in scanned records.\n')
 f.write('\n## Inputs\n\nHashes and per-file counts are in `audit.json`. Proposal SHA-256: `'+res['proposal_sha256']+'`. Six source receipt/audit hashes were checked against proposal references.\n')
