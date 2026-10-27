#!/usr/bin/env python3
"""Retained one-shot commands; no automatic retry or timeout escalation."""
import datetime
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).resolve().parent


def hashes():
    paths = [ROOT / 'Cargo.toml', ROOT / 'Cargo.lock', pathlib.Path(__file__).resolve()]
    paths += sorted((ROOT / 'crates/dodge-rl-env').rglob('*.rs'))
    paths += [ROOT / 'crates/dodge-rl-env/Cargo.toml']
    paths += [ROOT / p for p in json.loads((OUT / 'input-manifest.json').read_text())['frozen_pins']]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(name, command, timeout):
    attempts = list(OUT.glob(name + '-[0-9][0-9].log'))
    log = OUT / f'{name}-{len(attempts) + 1:02d}.log'
    before = hashes()
    start = time.monotonic()
    utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for path, expected in json.loads((OUT / 'input-manifest.json').read_text())['frozen_pins'].items():
        assert before[path] == expected, path
    if name == 'replay':
        state_path = ROOT / 'learning/runs/v2-orchestration/state.json'
        state = json.loads(state_path.read_text())
        assert state['active_long_campaign'] is None, 'another long campaign owns the lease'
        (OUT / 'pre-replay-lease-state.json').write_text(state_path.read_text())
        assert not attempts, 'replay already attempted; no automatic retry'
    with log.open('wb') as stream:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill exactly this command's owned process group, including a cargo
            # test child. Do not leave a replay running after a cargo timeout.
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code = 124
            stream.write(b'\nCHECKER_WALL_TIMEOUT_OWNED_PROCESS_GROUP_KILLED\n')
    receipt = {'name': name, 'command': command, 'utc_start': utc,
               'timeout_seconds': timeout, 'elapsed_seconds': time.monotonic() - start,
               'owned_pid_and_pgid': proc.pid, 'exit_code': code, 'log': log.name,
               'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
               'source_sha256': before, 'source_changed': before != hashes()}
    with (OUT / 'commands.jsonl').open('a') as f:
        f.write(json.dumps(receipt) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'source_sha256'}), flush=True)
    print(log.read_text()[-18000:], flush=True)
    return code


if __name__ == '__main__':
    name = sys.argv[1]
    raise SystemExit(run(name, sys.argv[2:], 120 if name == 'replay' else 360))
