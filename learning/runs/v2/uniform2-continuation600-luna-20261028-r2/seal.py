"""Exclusively seal owned source once; frozen predecessors are never resealed."""
import binding as b


if __name__ == '__main__':
    names = ('README.md', 'dependency-binding.json', 'registration-schema.json', 'blockers.json')
    files = sorted(p for p in b.HERE.iterdir() if p.is_file() and (p.suffix == '.py' or p.name in names))
    b.save(b.HERE/'source-manifest.json', dict(schema='uniform2_continuation600_source_manifest_v1', launch_authority=False,
                                               files={p.name: b.sha(p) for p in files}))
    print(b.sha(b.HERE/'source-manifest.json'))
