"""Inject at the actual outer cancellation-context unmask, after its pending drain.

Reuse the inspected immutable publication fixture, actual Guard and owned OS
worker. The only additional interception is the system unmask call; no candidate
source edits or runtime ML imports. Run only as an owned subprocess.
"""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r2'
sys.path.insert(0, str(PREP))
import publication_probes as probes

c = probes.c
root = Path(sys.argv[1]).resolve()
mutation, mode = sys.argv[2:4]
delay = float(sys.argv[4]) if len(sys.argv) > 4 else 0
if len(sys.argv) > 5:
    c.BUDGET = float(sys.argv[5])
real_mask = signal.pthread_sigmask
fired = False

def unmask(how, mask):
    global fired
    terminal = root / 'campaign/finalization-result.json'
    if (not fired and how == signal.SIG_SETMASK and c._ACTIVE_CANCELLATION is None
            and terminal.exists() and c.read_json(terminal)['experiment_status'] == 'complete'):
        fired = True
        event = dict(boundary='outer cancellation_signals finally: final SIG_SETMASK', mutation=mutation, delay_seconds=delay,
                     mode=mode, monotonic=time.monotonic(),
                     SIGINT_handler=str(signal.getsignal(signal.SIGINT)),
                     SIGTERM_handler=str(signal.getsignal(signal.SIGTERM)),
                     mask_before=sorted(int(v) for v in real_mask(signal.SIG_BLOCK, set())),
                     requested_mask=sorted(int(v) for v in mask),
                     active_latch_is_None=c._ACTIVE_CANCELLATION is None,
                     live_guard_threads=[t.name for t in threading.enumerate() if t.name.startswith('long-D2-')],
                     terminal_before=c.read_json(terminal),
                     manifest_before=(root / 'campaign/artifact-manifest.json').exists())
        if mutation in ('SIGINT', 'SIGTERM'):
            number = getattr(signal, mutation)
            os.kill(os.getpid(), number)
            event['real_signal_sent'] = int(number)
            event['pending_after_send'] = sorted(int(v) for v in signal.sigpending())
        elif mutation == 'cancel':
            state = root / 'state.json'
            value = c.read_json(state)
            value['active_long_campaign']['cancel_requested'] = True
            state.write_text(json.dumps(value))
        elif mutation == 'input':
            (root / 'watched.txt').write_text('changed at final outer unmask\n')
        (root / 'final-unmask-event.json').write_text(json.dumps(event, indent=2, sort_keys=True) + '\n')
        if delay:
            time.sleep(delay)
    return real_mask(how, mask)

with patch.object(signal, 'pthread_sigmask', side_effect=unmask):
    value = probes.scenario(root, phase='no-existing-trigger', mutation='none', mode=mode)
value['independent_final_unmask_trigger_fired'] = fired
(root / 'independent-observation.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
print(json.dumps(dict(return_code=value['return_code'], fired=fired)))
raise SystemExit(value['return_code'])
