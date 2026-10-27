"""Supplement existing native audit with retained original build archive/wheel checks."""
from datetime import datetime,timezone
import hashlib,json,tarfile,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BUILD=ROOT/'learning/runs/v2/milestone2-integration-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
r=read(BUILD/'build-receipt.json');pins=read(Path(r['source_manifest']))
archive_path=BUILD/'prebuild-source.tar.gz'
assert sha(archive_path)==r['source_archive_sha256']
with tarfile.open(archive_path,'r:gz') as archive:
 members=archive.getmembers();assert len(members)==len(pins)==62 and {m.name for m in members}==set(pins)
 for m in members:
  assert m.isfile() and hashlib.sha256(archive.extractfile(m).read()).hexdigest()==pins[m.name]
archived=BUILD/'native.cpython-312-darwin.so'
assert sha(archived)==r['archived_extension_sha256']==r['installed_extension_sha256']
wheels=list((BUILD/'wheels').glob('*.whl'));assert len(wheels)==1
with zipfile.ZipFile(wheels[0]) as wheel:
 so=[n for n in wheel.namelist() if n.endswith('.so')];assert len(so)==1
 assert hashlib.sha256(wheel.read(so[0])).hexdigest()==r['installed_extension_sha256']
binary=read(BUILD/'native-test-binary.json');assert binary['path']==r['native_test_binary'] and binary['sha256']==r['native_test_binary_sha256']
assert sha(Path(binary['path']))==binary['sha256']
# Cargo command is not JSON-formatted in retained logs; its explicitly retained
# selected compiler-artifact receipt fixes the executable and profile.
artifact=binary['compiler_artifact'];assert artifact['reason']=='compiler-artifact' and artifact['executable']==binary['path']
assert artifact['features']==[] and artifact['profile']['test'] and artifact['profile']['opt_level']=='3' and artifact['fresh'] is False
assert artifact['target']['name']=='dodge_rl_env'
selected=[archive_path,archived,wheels[0],BUILD/'native-test-binary.json',BUILD/'build-receipt.json',Path(r['source_manifest'])]
result={'status':'passed','at_utc':datetime.now(timezone.utc).isoformat(),'checker_sha256':sha(Path(__file__)),'original_source_archive_members':62,'archived_extension_matches_installed_pin':True,'matching_wheel_extension_members':so,'matching_wheel_extension_sha256':r['installed_extension_sha256'],'native_compiler_artifact':artifact,'input_sha256':{str(p):sha(p) for p in selected},'limitations':['Retained build receipts and artifacts establish hash lineage, not a new compiler execution or independent reproducible rebuild.','The release compilation log is not JSON compiler-artifact output; the separate native-test-binary receipt is the retained executable selection.']}
with (HERE/'build-lineage-supplement.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'status':result['status'],'supplement_sha256':sha(HERE/'build-lineage-supplement.json')}))
