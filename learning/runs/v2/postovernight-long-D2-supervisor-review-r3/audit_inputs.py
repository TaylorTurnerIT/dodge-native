"""Read-only input/provenance audit after the lifecycle blocker. No execution."""
import ast
import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREP = HERE.parent / 'postovernight-long-D2-prepare-r3'
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name, value): (HERE/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
initial = read(HERE/'input-sha256-manifest.json')['files']
expected = {str(ROOT/path):digest for path,digest in initial.items()}
inventory = read(PREP/'expanded-inventory.json')
for path,digest in inventory['full_pins'].items():
    assert path not in expected or expected[path]==digest, path
    expected[path]=digest
for folder in ('postovernight-long-D2-terminal-design-opus-r1','postovernight-long-D2-terminal-design-codex-r1'):
    for path in (HERE.parent/folder).iterdir():
        if path.is_file():expected.setdefault(str(path),sha(path))
observed={path:sha(Path(path)) for path in expected}
mismatches={path:dict(expected=expected[path],observed=observed[path]) for path in expected if expected[path]!=observed[path]}
write('input-sha256-manifest-expanded.json',dict(files=expected,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    initial_observed_count=len(initial), frozen_expanded_pins=len(inventory['full_pins']), new_pins_verified_against_registered_digests=True))
write('input-sha256-initial-expanded-verification.json',dict(files=len(expected), mismatches=mismatches))
assert not mismatches,mismatches
matrix=PREP/'attempts/matrix-final'
summary=read(matrix/'summary.json')
reconstructed=[]
for value in summary['results']:
    root=Path(value['argv'][-1])
    command=read(root/'observed-command.json')
    assert command==value,root
    events=[json.loads(line) for path in root.glob('*-events.jsonl') for line in path.read_text().splitlines()]
    assert bool([event for event in events if event['kind']=='injection'])==value['injection_reached'],root
    assert value['raw_wait']['returncode']==value['expected'],root
    assert value['elapsed_seconds']>=0 and all(value['positive_group_absence'].values()),root
    assert (root/'stdout.log').is_file() and (root/'stderr.log').is_file(),root
    reconstructed.append(dict(case=root.name,raw_exit=value['raw_wait']['returncode'],elapsed_seconds=value['elapsed_seconds'],
                              injection_reached=value['injection_reached'],groups=value['positive_group_absence']))
sources=read(matrix/'tested-sources.json')
source_match={name:dict(snapshot_sha256=sha(matrix/'sources'/name),declared=digest,current=sha(PREP/name)) for name,digest in sources.items()}
assert all(value['snapshot_sha256']==value['declared'] for value in source_match.values())
runtime=('long_d2.py','long_d2_executor.py','lifecycle.py','processes.py','synthetic.py','run_checks.py')
assert all(source_match[name]['current']==source_match[name]['declared'] for name in runtime)
units=read(PREP/'attempts/units-final-r2/unit-result.json')
assert all(sha(PREP/name)==digest for name,digest in units['sources'].items())
write('retained-evidence-audit.json',dict(new_execution=False, final_matrix_records=len(reconstructed),
    reported_matrix_count=summary['OS_subprocesses'], reconstructed=reconstructed,source_match=source_match,
    current_unit_receipt=units, aggregate_log_loss=read(PREP/'attempts/aggregate-log-note.json'),
    earlier_missing_stdout_recovered=False, missing_aggregate_not_needed_to_reconstruct_final_matrix=True,
    historical_pass_counts_transferred=False))
assert len(reconstructed)==summary['OS_subprocesses']
def nodes(path):
    source=path.read_text(); lines=source.splitlines(True)
    return {node.name:''.join(lines[node.lineno-1:node.end_lineno]) for node in ast.parse(source).body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
old=nodes(HERE.parent/'postovernight-long-D2-prepare-r2/long_d2.py');new=nodes(PREP/'long_d2.py')
names=read(PREP/'source-equality.json')['byte_equal_nodes']
equal={name:old[name]==new[name] for name in names}
write('source-comparison.json',dict(nodes_byte_identical=equal,worker_hook_diff_sha256=sha(PREP/'worker-hook.diff'),
    interpretation='Static byte identity only; no ML/runtime API verification.'))
assert all(equal.values())
print(json.dumps(dict(input_count=len(expected), mismatches=len(mismatches), retained_matrix_records=len(reconstructed),
                     current_runtime_sources_match=True, protected_nodes=len(equal))))
