"""Exclusively seal owned source once; never reseal a reviewed predecessor."""
from pathlib import Path
import binding as b


if __name__=='__main__':
    files=sorted(p for p in b.HERE.iterdir() if p.is_file() and
        (p.suffix=='.py' or p.name in ('README.md','dependency-binding.json','policy-plan.json','registration-schema.json')))
    b.save(b.HERE/'source-manifest.json',dict(schema='fullgame_priority_d4_evaluation_source_manifest_v1',
        launch_authority=False,files={p.name:b.sha(p) for p in files}))
    print(b.sha(b.HERE/'source-manifest.json'))
