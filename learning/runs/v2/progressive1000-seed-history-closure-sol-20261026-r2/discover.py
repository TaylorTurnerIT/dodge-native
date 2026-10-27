"""Read-only, stdlib provenance index. All writes stay beside this file."""
import collections
import hashlib
import json
import os
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R1 = ROOT / 'learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1'
PINS = {}
BLOCK = re.compile(r'(?i)(qualification|holdout|(?<![a-z0-9])(?:B1000|E1000)(?![a-z0-9])|(?:^|[/_-])(?:B|E)(?:-campaign|-execution|-evaluation|/outputs)|native.parity|gate-baselines|baseline_expected|baseline-replay|baseline-selection|milestone0-campaign|full-audit|profile-audit)')
COPY = re.compile(r'/(?:provenance|history|source-before|originals|source|runtime|capsule|attempts)/')
FIXTURE = re.compile(r'(?i)(fixture|synthetic|fake[-_/]|test-tmp|test_tmp|pytest|/test_|/tests?(?:/|-and-receipts/)|reproduction|/positive-controls/|/negative|/case[-_/]|/cases/|replay[-_])')
META = re.compile(r'(?i)(seed|episode|counter|run_id|status|error|failure|traceback|command|argv|constructor|reset|attempt|launch|updates|step_calls|batch_size|initial|resume|identity|registration|runtime_root|runner_path|source|sha256|checkpoint_path|output|directory|exit|returncode|training_eligible|diagnostic_only)')

def read(path, purpose):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    rel = str(path.relative_to(ROOT))
    assert not BLOCK.search(rel), rel
    assert path.suffix not in ('.pt', '.so', '.dylib', '.npy', '.npz'), rel
    data = path.read_bytes()
    row = {'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'purposes': [purpose]}
    if rel in PINS:
        assert PINS[rel]['sha256'] == row['sha256'], rel
        row['purposes'] = sorted(set(PINS[rel]['purposes'] + row['purposes']))
    PINS[rel] = row
    return data

def load(path, purpose='seed/counter/identity provenance'):
    return json.loads(read(path, purpose))

def write(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')

def walk(obj, ptr=''):
    if isinstance(obj, dict):
        yield ptr, obj
        for k, v in obj.items():
            yield from walk(v, ptr + '/' + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, ptr + '/' + str(i))

def projection(obj):
    out = []
    for ptr, row in walk(obj):
        for k, v in row.items():
            if META.search(k) and not isinstance(v, dict):
                if isinstance(v, list) and len(v) > 150:
                    v = {'length': len(v), 'head': v[:3], 'tail': v[-3:]}
                out.append([ptr + '/' + k, v])
    return out

def main():
    inventory = load(R1 / 'coverage-inventory.json', 'complete R1 path inventory')
    unresolved = {r['path'] for r in inventory if r['category'] == 'unresolved_execution_provenance'}
    index, logs, denied, errors = [], [], [], []
    for base, dirs, files in os.walk(ROOT / 'learning/runs', followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ('__pycache__', 'empty-pycache', '.git') and (Path(base) / d) != HERE)
        for name in sorted(files):
            p = Path(base) / name
            rel = str(p.relative_to(ROOT))
            if BLOCK.search(rel):
                denied.append(rel)
                continue
            if COPY.search(rel) or FIXTURE.search(rel):
                continue
            if '/progressive1000-seed-cohort-prepare-' in rel or '/progressive1000-seed-r1-parent-validation-' in rel:
                continue
            outside = not rel.startswith('learning/runs/v2/')
            if p.suffix in ('.json', '.jsonl'):
                # Mixed campaign receipts may embed qualification parity outcomes.
                if '/milestone2-validation-campaign-' in rel and name in ('campaign-result.json', 'identity.json'):
                    denied.append(rel)
                    continue
                try:
                    data = read(p, 'original provenance index; outside-v2' if outside else 'original provenance index')
                    if p.suffix == '.jsonl':
                        rows = [json.loads(s) for s in data.splitlines() if s.strip()]
                        # Aggregate seed metadata and terminal counters; no quality projection.
                        vals = collections.defaultdict(set)
                        for row in rows:
                            for ptr, item in walk(row):
                                for k,v in item.items():
                                    if type(v) is int and ('seed' in k or k in ('episode','slot','counter','step_call')):
                                        vals[k].add(v)
                        meta = {k: {'count':len(v),'min':min(v),'max':max(v)} for k,v in vals.items() if v}
                        index.append({'path':rel, 'rows':len(rows), 'summary':meta, 'first_metadata':projection(rows[:1]), 'last_metadata':projection(rows[-1:]), 'r1_unresolved':rel in unresolved})
                    else:
                        obj = json.loads(data)
                        index.append({'path':rel, 'metadata':projection(obj), 'r1_unresolved':rel in unresolved})
                except (ValueError, UnicodeError) as e:
                    errors.append({'path':rel,'error':str(e)})
            elif p.suffix in ('.log','.txt','.out','.stderr','.stdout') and name != 'README.md':
                data = read(p, 'non-JSON episode/launch provenance').decode(errors='replace')
                hits = [[i,line[:1200]] for i,line in enumerate(data.splitlines(),1) if re.search(r'(?i)(seed|episode|reset|VecDodgeEnv|run.id|Traceback|Error|exit|_worker|constructor)',line)]
                logs.append({'path':rel,'lines':len(data.splitlines()),'metadata_lines':hits})
    write('provenance-index.json', index)
    write('non-json-index.json', logs)
    write('discovery-boundary.json', {'denied_unopened':denied,'errors':errors,'indexed_files':len(index),'non_json_files':len(logs),'r1_unresolved_paths':len(unresolved)})
    write('discovery-input-pins.json',list(PINS.values()))
    print(json.dumps({'index':len(index),'logs':len(logs),'denied':len(denied),'errors':len(errors)}))

if __name__ == '__main__':
    main()
