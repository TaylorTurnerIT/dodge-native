from pathlib import Path
import datetime,hashlib,json,subprocess,sys,tarfile,traceback
r=Path(__file__).resolve().parent
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
log=r/'final-verification.log'
try:
 manifest=json.loads((r/'source-manifest.json').read_text())
 source=manifest['workspace_check_source_sha256']
 for p,h in source.items(): assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 with tarfile.open(r/'source.tar.gz','r:gz') as archive:
  for p,h in source.items():
   f=archive.extractfile(p);assert f is not None,p
   assert hashlib.sha256(f.read()).hexdigest()==h,p
 for artifact,key in [('source.tar.gz','archive_sha256'),('milestone2-core.patch','patch_sha256'),('before-owned-source.tar.gz','before_owned_archive_sha256')]:
  assert hashlib.sha256((r/artifact).read_bytes()).hexdigest()==manifest[key],artifact
 count=0
 for p in sorted(r.rglob('*.json')):
  result=subprocess.run([sys.executable,'-m','json.tool',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
  assert result.returncode==0,(str(p),result.stderr)
  count+=1
 required=['fmt-workspace','clippy-workspace-first','test-workspace','diff-check']
 for name in required:
  d=json.loads((r/(name+'.json')).read_text());assert d['source_sha256']==source;assert not d['source_changed_during_check'];assert d['exit_code']==0
 verification=json.loads((r/'verification.json').read_text());assert verification['elapsed_seconds_since_062028_utc']<2700
 text=f'PASS: {count} JSON files validated with python3 -m json.tool; {len(source)} workspace source hashes checked against current files and archive. Required checks pin identical source. Source remains frozen.\n'
 log.write_text(text)
 receipt={'command':[sys.executable,str(Path(__file__))],'utc_start':start,'exit_code':0,'raw_log':'final-verification.log','json_files_validated_before_this_receipt':count,'workspace_source_files_verified':len(source),'archive_member_hashes_verified':True,'required_checks_match_frozen_source':True,'source_frozen':True}
 (r/'final-verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
 # Exclude only this hash index. Its own hash is returned to the parent.
 hashes={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file() and p.name!='artifact-sha256.json'}
 (r/'artifact-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
 for p in [r/'final-verification.json',r/'artifact-sha256.json']:
  subprocess.run([sys.executable,'-m','json.tool',str(p)],stdout=subprocess.DEVNULL,check=True)
 print(text.strip());print('artifact-sha256.json SHA256:',hashlib.sha256((r/'artifact-sha256.json').read_bytes()).hexdigest())
 print('Source SHA256:',json.dumps(manifest['source_sha256'],indent=2))
except BaseException:
 log.write_text(traceback.format_exc())
 (r/'final-verification.json').write_text(json.dumps({'command':[sys.executable,str(Path(__file__))],'utc_start':start,'exit_code':1,'raw_log':'final-verification.log'},indent=2)+'\n')
 raise
