"""Run one unblocked control and one new-purpose interruptible-IO diagnostic."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r3'
sys.path.insert(0, str(PREP))
import long_d2 as c
import long_d2_executor as e
import synthetic
import processes as owned

def run(name, block):
    root = HERE / name
    root.mkdir()
    (root / 'capsule-manifest.json').write_text('{"files":{}}')
    (root / 'watched.txt').write_text('frozen input\n')
    (root / 'module.py').write_text('# synthetic origin bytes only\n')
    (root / 'pins.json').write_text(json.dumps({str(root / k): c.sha(root / k) for k in ('watched.txt','module.py')}))
    (root / 'options.json').write_text(json.dumps(dict(mode='closure', worker_seconds=2.5, inner_seconds=3, outer_seconds=4)))
    lease = c.expected_lease({**synthetic.P,'output':'campaign'},'a'*64,'b'*64,root,'c'*64)
    (root / 'state.json').write_text(json.dumps({'active_long_campaign':lease}))
    argv = [sys.executable,'-B',str(HERE/'probe_final_io.py'),str(root),'block' if block else 'control']
    started = time.monotonic()
    event = None
    killed = False
    with (root/'stdout.log').open('x') as stdout, (root/'stderr.log').open('x') as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        while process.poll() is None:
            event_path = root/'final-read-event.json'
            if event is None and event_path.exists():
                event = json.loads(event_path.read_text())
            until = event['latest_shared_cap']+.5 if block and event else started+18
            if time.monotonic() >= until:
                # This is a test-harness termination, not candidate cleanup.
                killed = True
                killed_at = time.monotonic()
                process.kill()
                break
            time.sleep(.01)
        process.wait(timeout=1)
    elapsed = time.monotonic()-started
    receipt_path = root/'execution/acceptance-receipt.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    if event is None and (root/'final-read-event.json').exists():
        event = json.loads((root/'final-read-event.json').read_text())
    absence = {key:owned.absent(record['pgid'],time.monotonic()+.2) for key,record in receipt.get('ownership',{}).items()}
    result = dict(argv=argv, raw_exit=process.returncode, elapsed_seconds=elapsed, injection_reached=event is not None,
                  blocked=block, harness_kill_required=killed, receipt_accepted=receipt.get('accepted'),
                  observed_acceptance=e.accept_observed(receipt,process.returncode,elapsed),
                  positive_group_absence=absence, event=event,
                  exceeded_latest_shared_cap=(killed_at-event['latest_shared_cap'] if killed and event else None),
                  process_reaped=True, ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')])
    (root/'observed-command.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('event','argv')}), flush=True)
    assert event is not None, 'final post-watchdog verifier was not reached'
    assert all(absence.values()) and len(absence)==2, absence
    if not block:
        assert process.returncode==2 and not killed and result['observed_acceptance'], result
    return result

results = [run('final-io-unblocked-control',False), run('final-io-blocked-diagnostic',True)]
(HERE/'final-io-summary.json').write_text(json.dumps(results,indent=2)+'\n')
# Required property; its assertion failure is retained review evidence.
assert not results[-1]['harness_kill_required'], 'Executor remained alive past its normal deadline and entire shared failure cap in post-watchdog normal verification'
