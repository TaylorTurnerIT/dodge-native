"""Bounded serial subprocess driver, retaining exact commands and all results."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
records = []
for mutation in ('none', 'SIGINT', 'SIGTERM', 'cancel', 'input'):
    for mode in ('closure', 'pass'):
        root = HERE / ('final-unmask-' + mutation + '-' + mode)
        argv = [sys.executable, '-B', str(HERE / 'probe_final_unmask.py'), str(root), mutation, mode]
        run = subprocess.run(argv, capture_output=True, text=True, timeout=25,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(HERE / 'tmp')))
        (HERE / (root.name + '.log')).write_text(run.stdout + run.stderr)
        terminal = root / 'campaign/finalization-result.json'
        value = dict(name=root.name, argv=argv, process_exit=run.returncode,
                     injection_event_available=(root / 'final-unmask-event.json').exists(),
                     observation_available=(root / 'independent-observation.json').exists())
        if terminal.exists():
            value['terminal'] = json.loads(terminal.read_bytes())
            value['manifest_available'] = (root / 'campaign/artifact-manifest.json').exists()
            rr = json.loads((root / 'campaign/long-run-result.json').read_bytes())
            value['owned_stop'] = rr.get('owned_process_stop')
            pgid = (value['owned_stop'] or {}).get('owned_pgid')
            value['owned_group_positively_absent'] = False
            if pgid:
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    value['owned_group_positively_absent'] = True
        records.append(value)
        (HERE / 'independent-probe-summary.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
        print(json.dumps({k:v for k,v in value.items() if k not in ('terminal','argv','owned_stop')}), flush=True)
