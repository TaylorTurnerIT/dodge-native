"""Independent stdlib-only supervisor boundary probes; no production invocation."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r1'
spec = importlib.util.spec_from_file_location('candidate_synthetic_tests', PREP / 'test_long_d2.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
c = t.c


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def scenario(name):
    root = (HERE / name).resolve()
    root.mkdir()
    output = root / 'campaign'
    state = root / 'state.json'
    watched = root / 'watched-input.txt'
    watched.write_text('frozen synthetic input\n')
    pins = {str(watched): c.sha(watched)}
    write(state, {'active_long_campaign': t.lease()})
    (root / 'capsule-manifest.json').write_text('{"files":{}}')
    protocol = {**t.PROTOCOL, 'output': 'campaign'}
    context = protocol, t.CONFIG, t.BASE, {}, pins, t.lease()
    args = types.SimpleNamespace(output=output, state_path=state)
    real_stop, real_sha, real_alarm = c.stop_owned, c.sha, c.absolute_alarm
    events = []
    fired = [False]
    started = time.monotonic()
    short = name in ('late-final-verify', 'late-artifact-hash')

    def event(kind, **fields):
        events.append(dict(kind=kind, elapsed=time.monotonic()-started, **fields))
        write(root / 'events.json', events)

    class FixtureGuard(t.FakeGuard):
        def close(self):
            event('guard_closed')

    class RealGuard(c.Guard):
        def close(self):
            super().close()
            event('real_guard_closed', receipt=self.receipt())

    def command(*unused):
        return [sys.executable, '-B', str(PREP / 'fake_worker.py'), '--output', str(output),
                '--mode', 'pass' if name == 'late-lease-cancel-pass' else 'closure']

    def stopped(process):
        receipt = real_stop(process)
        event('owned_stop', receipt=receipt)
        if name == 'unproven-group':
            receipt['group_empty'] = False
        if name == 'deferred-cleanup-cancel':
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGTERM)
        return receipt

    def verify(actual):
        c.verify_files_original(actual)
        event('input_verification')
        if name == 'deferred-final-verify-cancel':
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGINT)
        if name == 'late-final-verify':
            time.sleep(1.2)

    def hashing(path):
        path = Path(path)
        if path.is_relative_to(output) and not fired[0] and not name.startswith('outer-alarm-'):
            fired[0] = True
            event('first_artifact_hash', file=path.name)
            if name.startswith('late-lease-cancel'):
                value = c.read_json(state)
                value['active_long_campaign']['cancel_requested'] = True
                write(state, value)
                event('lease_cancellation_written')
                time.sleep(0.65)
            if name.startswith('late-input-change'):
                watched.write_text('changed after final verification\n')
                event('pinned_input_changed')
                time.sleep(0.65)
            if name == 'late-artifact-hash':
                time.sleep(1.2)
        return real_sha(path)

    @contextmanager
    def alarm(deadline):
        with real_alarm(deadline):
            yield
        terminal = output / 'finalization-result.json'
        if name.startswith('outer-alarm-') and terminal.exists() and not fired[0]:
            if c.read_json(terminal).get('experiment_status') == 'complete':
                fired[0] = True
                number = signal.SIGTERM if name.endswith('SIGTERM') else signal.SIGINT
                event('signal_at_outer_publication_alarm_exit', signal=number,
                      current_handler=str(signal.getsignal(number)))
                os.kill(os.getpid(), number)

    c.verify_files_original = c.verify_files
    with patch.object(c, 'ORIGINAL_ROOT', root), patch.object(c, 'ROOT', root), \
         patch.object(c, 'STATE_PATH', state), patch.object(c, 'assert_readonly_capsule'), \
         patch.object(c, 'stop_owned', side_effect=stopped), \
         patch.object(c, 'verify_files', side_effect=verify), patch.object(c, 'sha', side_effect=hashing), \
         patch.object(c, 'BUDGET', 0.8 if short else 7200):
        code = c.supervise(args, context_provider=lambda unused: context,
                           command_factory=command,
                           guard_factory=RealGuard if name.endswith('real-guard') else FixtureGuard,
                           alarm_factory=alarm, started=started)
    terminal = c.read_json(output / 'finalization-result.json')
    result = c.read_json(output / 'long-run-result.json')
    manifest = output / 'artifact-manifest.json'
    observed = dict(scenario=name, return_code=code, terminal=terminal,
                    manifest_available=manifest.exists(), events=events,
                    lease_cancel_requested=c.read_json(state)['active_long_campaign']['cancel_requested'],
                    pinned_input_still_matches=real_sha(watched) == pins[str(watched)],
                    no_ML_imports=not any(n == 'torch' or n.startswith(('torch.', 'numpy', 'dodge_rl'))
                                          for n in sys.modules))
    if manifest.exists():
        observed['manifest_binding_matches'] = terminal['artifact_manifest_sha256'] == real_sha(manifest)
        observed['run_binding_matches'] = terminal['run_result_sha256'] == real_sha(output / 'long-run-result.json')
    observed['cleanup'] = result.get('owned_process_stop')
    write(root / 'observation.json', observed)
    print(json.dumps({k: observed[k] for k in ('scenario', 'return_code', 'manifest_available',
          'lease_cancel_requested', 'pinned_input_still_matches', 'no_ML_imports')}), flush=True)
    return observed


def main():
    if len(sys.argv) > 1:
        scenario(sys.argv[1])
        return
    results = []
    for name in ('late-final-verify', 'late-artifact-hash', 'unproven-group',
                 'deferred-cleanup-cancel', 'deferred-final-verify-cancel',
                 'late-lease-cancel', 'late-lease-cancel-pass', 'late-input-change',
                 'outer-alarm-SIGINT', 'outer-alarm-SIGTERM'):
        run = subprocess.run([sys.executable, '-B', __file__, name], capture_output=True,
                             text=True, timeout=20,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(HERE/'tmp')))
        (HERE / (name + '.log')).write_text(run.stdout + run.stderr)
        root = HERE / name
        result = dict(scenario=name, process_exit=run.returncode,
                      log=name+'.log', observation_available=(root/'observation.json').exists())
        if (root/'campaign/finalization-result.json').exists():
            terminal = json.loads((root/'campaign/finalization-result.json').read_bytes())
            result.update(terminal_status=terminal['experiment_status'], outcome=terminal['outcome'],
                          manifest_available=(root/'campaign/artifact-manifest.json').exists())
        results.append(result)
        print(json.dumps(result), flush=True)
    write(HERE/'probe-summary.json', results)


if __name__ == '__main__':
    main()
