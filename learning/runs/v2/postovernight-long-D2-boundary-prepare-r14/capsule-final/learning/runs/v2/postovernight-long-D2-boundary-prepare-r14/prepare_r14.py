"""Read-only r12 verification and owned r14 source-only copy. Routine read
inspection errors are retained separately; hash mismatch stops without patch."""
from pathlib import Path
import datetime, hashlib, json, shutil

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
R12 = H.with_name('postovernight-long-D2-boundary-prepare-r12')
SKIP_CURRENT = {'test_r12.py', 'prepare_r12.py', 'finalize_r12.py', 'run_unit_suite.py', 'unit_stage.py'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    with (H / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def main():
    try:
        source = json.loads((R12 / 'source-manifest.json').read_text())['files']
        bad = [n for n, v in source.items() if sha(R12 / n) != v['sha256'] or (R12 / n).stat().st_size != v['bytes']]
        if bad or len(source) != 229:
            raise RuntimeError('r12 source hash mismatch: %r count=%d' % (bad[:5], len(source)))
        inputs = json.loads((R12 / 'input-manifest.json').read_text())['files']
        bad_in = [n for n, v in inputs.items() if sha(n) != v['sha256']]
        if bad_in or len(inputs) != 215:
            raise RuntimeError('r12 input hash mismatch: %r count=%d' % (bad_in[:5], len(inputs)))
        evidence = json.loads((R12 / 'evidence-manifest.json').read_text())['files']
        bad_ev = [n for n, v in evidence.items() if sha(R12 / n) != v['sha256']]
        if bad_ev:
            raise RuntimeError('r12 evidence hash mismatch: %r' % (bad_ev[:5],))
        authority = ROOT / 'learning/runs/v2-orchestration'
        extra = {}
        for name in ('postovernight-long-D2-boundary-repair-r14-task.md', 'postovernight-long-D2-boundary-repair-r13-task.md',
                     'postovernight-long-D2-boundary-repair-r12-task.md', 'postovernight-long-D2-r13-parent-reconciliation.json',
                     'postovernight-long-D2-r12-parent-reconciliation.json'):
            extra[str(authority / name)] = sha(authority / name)
        probe = ROOT / 'learning/runs/v2/postovernight-long-D2-switchinterval-probe-r1'
        for name in ('probe_once.py', 'run_once.py', 'plan.json', 'command.json', 'wrapper-result.json',
                     'output/result.json', 'parent-reconciliation.json', 'parent-evidence-manifest.json'):
            extra[str(probe / name)] = sha(probe / name)
        chron = ROOT / 'learning/runs/v2/postovernight-long-D2-r12-chronology-proof-r1'
        for path in sorted(chron.rglob('*')):
            if path.is_file():
                extra[str(path)] = sha(path)
        state = (authority / 'state.json').read_bytes()
        (H / 'state.context.snapshot.json').write_bytes(state)
        # Current files: every top-level r12 source member except r12-specific scripts.
        r12snap = H / 'r12-source'
        r12snap.mkdir()
        copies = {}
        for name in source:
            if '/' in name:
                continue
            shutil.copyfile(R12 / name, r12snap / name)
            if name not in SKIP_CURRENT:
                shutil.copyfile(R12 / name, H / name)
                copies[name] = sha(H / name)
        for name in ('original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source'):
            shutil.copytree(R12 / name, H / name)
            shutil.copytree(R12 / name, r12snap / name)
        save('base-source-manifest.json', dict(schema='r14_base_v1', base=str(R12), base_candidate='frozen r12',
            r12_source_members_verified=len(source), r12_input_members_verified=len(inputs),
            r12_evidence_members_verified=len(evidence), current_top_level_copies=copies,
            skipped_r12_specific_current=sorted(SKIP_CURRENT), r12_snapshot=str(r12snap),
            retained_fixture_directories=['original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source']))
        save('input-manifest.json', dict(schema='r14_inputs_v1', r12_inputs=inputs, additional_inputs=extra,
            r12_source_members=len(source), r12_input_members=len(inputs), r12_evidence_members=len(evidence),
            additional_input_count=len(extra), mutable_context_snapshot='state.context.snapshot.json',
            read_without_execution=True))
        print(json.dumps(dict(status='prepared', source=len(source), inputs=len(inputs), evidence=len(evidence), extra=len(extra))))
    except BaseException as error:
        save('setup-failure.json', dict(error=repr(error), no_retry=True))
        raise

if __name__ == '__main__':
    main()
