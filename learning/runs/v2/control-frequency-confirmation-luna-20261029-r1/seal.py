"""Seal owned source exactly once; source manifest grants no launch authority."""
from pathlib import Path
import binding as b
if __name__=='__main__':
    b.need(not (b.HERE/'source-manifest.json').exists(),'source already sealed; never reseal reviewed source')
    files=sorted(p for p in b.HERE.iterdir() if p.is_file() and (p.suffix=='.py' or p.name in ('README.md','source-delta.md','dependency-binding.json','policy-plan.json','registration-schema.json','package-manifest.json')))
    b.save(b.HERE/'source-manifest.json',dict(schema='control_frequency_confirmation_source_manifest_v1',launch_authority=False,files={p.name:b.sha(p) for p in files}))
    print(b.sha(b.HERE/'source-manifest.json'))
