"""Compile and run exactly one bounded supplemental public-API probe."""
import hashlib,json,pathlib,subprocess,sys
from check import ROOT,OUT,run
if '--parse-only' not in sys.argv:
 rlibs=list((ROOT/'target/debug/deps').glob('libdodge_rl_env-*.rlib'))
 assert len(rlibs)==1,rlibs
 source=OUT/'trajectory_probe.rs';exe=OUT/'trajectory_probe'
 (OUT/'trajectory-inputs.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rlib':str(rlibs[0]),'rlib_sha256':hashlib.sha256(rlibs[0].read_bytes()).hexdigest()},indent=2)+'\n')
 code=run('trajectory-build',['rustc','+1.97.1','--edition','2024','--deny','warnings',str(source),'-L','dependency='+str(ROOT/'target/debug/deps'),'--extern','dodge_rl_env='+str(rlibs[0]),'-o',str(exe)],60)
 if code:sys.exit(code)
 code=run('trajectory',[str(exe)],60)
 if code:sys.exit(code)
receipts=[json.loads(line) for line in (OUT/'commands.jsonl').read_text().splitlines()]
probe=[r for r in receipts if r['name']=='trajectory']
assert len(probe)==1 and probe[0]['exit_code']==0,probe
text=(OUT/probe[0]['log']).read_text();reference=[json.loads(l.split(' ',1)[1]) for l in text.splitlines() if l.startswith('SEED_REFERENCE ')]
mask=(1<<64)-1

def mix(z):
 z=((z^(z>>30))*0xBF58476D1CE4E5B9)&mask
 z=((z^(z>>27))*0x94D049BB133111EB)&mask
 return z^(z>>31)
for row in reference:
 base=mix(row['run']^0x444F4447455F5632)^mix((row['slot']+0x9E3779B97F4A7C15)&mask)^mix((row['episode']+0xD1B54A32D192ED03)&mask)
 counter=0
 while True:
  seed=mix(base^mix((counter+0x94D049BB133111EB)&mask))>>32
  if not 0xB0000000<=seed<=0xB00003E7:break
  counter+=1
 assert (counter,seed)==(row['counter'],row['actual_seed']),row
assert len(reference)==16
summary=json.loads(next(l.split(' ',1)[1] for l in text.splitlines() if l.startswith('TRAJECTORY ')))
(OUT/'trajectory.json').write_text(json.dumps({'status':'passed','source_and_binary':'trajectory-inputs.json','results':summary,'independent_python_seed_vectors_checked':len(reference),'seed_vectors':reference,'scope':'Owned public arrays/metadata and explicit partial resets; longer complement to normal crate canonical-state thread test. No throughput or memory claim.'},indent=2)+'\n')
