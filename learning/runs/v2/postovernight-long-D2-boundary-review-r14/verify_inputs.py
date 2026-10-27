import pathlib,hashlib,json,datetime,sys
root=pathlib.Path.cwd(); out=root/'learning/runs/v2/postovernight-long-D2-boundary-review-r14'; c=root/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
pins=json.loads((c/'parent-frozen-pins.json').read_text()); assert len(pins)==8
expected=['209b03f19c08355ca05c66acd366465cc784ebf376cf1c238403a39ef4eafbc5','b63d5356beb88c801ce4f8d5ccd82d5df1c65d32b6e955c72899c41cd3ffbdd4','aab36d678526b6fbd4eecbe1493ad3511365f00064a91d459b85834eaf3e752b','d4aafd463d105967b44151f11ec8e1c5fb5d5b633c6892db8bde829f28eff560','c1cb6783c1b39758b8fbf1a0414edf246a84bd394525c51179f80d746c2509ad','3c5edeb8648506d3587785099c46dee0747c58dadd00cea188b41894bf7e8eb9','0bc28db76eda281b78ea2c8189703c5badd0876d1024813e6c7b67b4c98c1d0d','421eb3df6858ecacbe22d7abd83cd5ed5e2e1e02391b60ff3eb92caa8f3da369']; assert set(pins.values())==set(expected)
checks={p:{'expected':s,'actual':sha(root/p)} for p,s in pins.items()}
p='learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r10.json';checks[p]={'expected':'ff160f8faec7c4d9b165e09db38fc3831e20e3f6609f1a82b63df42a307979ec','actual':sha(root/p)}
r={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'all_match':all(x['expected']==x['actual'] for x in checks.values())}
(out/('pins-'+sys.argv[1]+'.json')).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));assert r['all_match']
if sys.argv[1]=='before':
 (out/'start.json').write_text(json.dumps({'at_utc':r['at_utc'],'budget_seconds':900,'scope':'fresh frozen r14 readonly source review; no project imports or suite/runtime execution'},indent=2)+'\n')
 (out/'state.context.before.json').write_bytes((root/'learning/state.json').read_bytes()) if (root/'learning/state.json').exists() else None
