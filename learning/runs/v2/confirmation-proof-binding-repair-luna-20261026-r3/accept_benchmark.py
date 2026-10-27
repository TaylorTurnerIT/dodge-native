"""Inert stdlib adapter: bind worker benchmark evidence to supervisor postflight."""
import hashlib,json,os,uuid
from pathlib import Path

SCHEMA='expanded_eval_accepted_benchmark_evidence_v1'
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read(p): return json.loads(Path(p).read_text())
def accept(*,worker_path,worker_sha256,outer_path,outer_sha256,output_path):
 if sha(worker_path)!=worker_sha256 or sha(outer_path)!=outer_sha256:raise ValueError('external worker/outer receipt pin mismatch')
 worker=read(worker_path);outer=read(outer_path)
 if worker.get('schema')!='expanded_eval_dev64_benchmark_receipt_v1' or worker.get('complete') is not True:raise ValueError('raw worker receipt identity/incomplete')
 if outer.get('schema')!='expanded_eval_outer_receipt_v1' or outer.get('raw_exit_code')!=0 or outer.get('stop_reason') is not None or outer.get('process_group_absent') is not True:raise ValueError('supervisor outer receipt did not pass postflight')
 for field,want in (('stage','benchmark'),('candidate_update',348),('cohort','benchmark_dev64')):
  if outer.get(field)!=want:raise ValueError('outer receipt '+field+' mismatch')
 if outer.get('run_id')!=worker.get('run_id') or outer.get('registration_sha256')!=worker.get('registration_sha256'):raise ValueError('worker/outer run or registration identity mismatch')
 artifacts=outer.get('output_artifacts'); expected_output=os.path.abspath(os.fspath(worker_path)); matches=[a for a in artifacts or [] if a.get('path')==expected_output]
 if len(matches)!=1 or matches[0].get('sha256')!=worker_sha256:raise ValueError('outer receipt does not bind exact worker output path/hash')
 out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True)
 wrapper={'schema':SCHEMA,'complete':True,'run_id':worker['run_id'],'registration_sha256':worker['registration_sha256'],'worker_receipt_path':expected_output,'worker_receipt_sha256':worker_sha256,'outer_receipt_path':os.path.abspath(os.fspath(outer_path)),'outer_receipt_sha256':outer_sha256,'stage_output_path':expected_output,'stage_output_sha256':worker_sha256}
 tmp=out.with_name(out.name+'.'+uuid.uuid4().hex+'.tmp');fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(wrapper,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.link(tmp,out);tmp.unlink();return out
