from pathlib import Path
import hashlib,json,shutil,datetime,subprocess
root=Path.cwd();base=root/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r10';out=base.with_name('postovernight-long-D2-boundary-prepare-r11')
assert not out.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins=json.loads((base/'parent-frozen-pins.json').read_text());assert len(pins)==8
for path,digest in pins.items():assert sha(root/path)==digest,(path,digest)
auth={
'learning/runs/v2-orchestration/postovernight-long-D2-boundary-review-r10-parent-reconciliation.json':'b8401edfa2ec2106dcc4ba7b00f841e008619cfa94572314f426d54ac2886594',
'learning/runs/v2-orchestration/postovernight-long-D2-escalation-reap-sonnet-r1-parent-reconciliation.json':'83fc23ac9dac6a1898f1b2d6301b1c3b79ba7fb3e45dedba3d4c3c67a8c7b642',
'learning/runs/v2-orchestration/postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json':'95977b36b45ad1ea670a601b51bb70198d0c0f37bb76c237b6ac032e535ebe9d',
'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r7.json':'49b25af4181353cc6d31b03c3666475c37eb5a433b4038d4cc4076519420ebce'}
for path,digest in auth.items():assert sha(root/path)==digest,path
out.mkdir();(out/'r10-source').mkdir()
for p in base.glob('*.py'):
 shutil.copyfile(p,out/p.name);shutil.copyfile(p,out/'r10-source'/p.name)
for name in ('original-source','r6-source','r9-source'):shutil.copytree(base/name,out/name)
for name in ('preparation-copy.json','retained-r9-injection.json','PARENT-NEXT.md','protocol-r7-proposal.json'):
 shutil.copyfile(base/name,out/name);shutil.copyfile(base/name,out/'r10-source'/name)
shutil.copyfile(root/'learning/runs/v2-orchestration/state.json',out/'state.context.snapshot.json')
(out/'input-pins.json').write_text(json.dumps(dict(schema='r11_input_pins_v1',verified_before_copy=True,parent_frozen_pins=pins,authorities=auth,base_sources={str(p.relative_to(base)):sha(p) for p in base.glob('*.py')},started_at_utc='2026-10-25T03:07:57+00:00',copy_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state_context_only=True),indent=2)+'\n')
(out/'workspace-before.txt').write_text(subprocess.check_output(['git','status','--porcelain=v1'],text=True))
print(out)
