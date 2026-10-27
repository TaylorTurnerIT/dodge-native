"""Separate-process deterministic runtime comparison; config only, no envs."""
import json,os,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parent
new=str(base.parent/'D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime')
# Candidate directory ancestry is variable; resolve baseline from workspace spec marker.
root=next(parent for parent in base.parents if (parent/'docs/SPEC_PRIVILEGED_VIT_RL.md').is_file())
old=str(root/'learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime')
env=os.environ.copy(); env.pop('PYTHONPATH',None)
def run(runtime):
    return json.loads(subprocess.check_output([sys.executable,'-B',str(base/'smoke_runtime.py'),runtime],cwd=base,env=env,text=True))
a=run(new); b=run(old)
origins={'new':a.pop('module_origins'),'baseline':b.pop('module_origins')}
assert a==b, 'canonical protocol/seeds/D2 configs differ'
assert all(str(Path(value).resolve()).startswith(new) for value in origins['new'].values()), origins
result={'status':'passed','protocol_equal':True,'development_seed_count':len(a['seeds']),'D2_config_rows':len(a['rows']),'module_origins':origins}
# Receipt is emitted only to stdout; registration pins exclude generated artifacts.
print(json.dumps(result,sort_keys=True))
