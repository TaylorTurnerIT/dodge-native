#!/usr/bin/env python3
"""Synthetic supervisor fixture. No project/ML/native imports or gameplay."""
import argparse
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import time
p=argparse.ArgumentParser()
p.add_argument('--output',type=Path,required=True)
p.add_argument('--mode',default='closure')
a=p.parse_args()
if a.mode=='blocked':
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True:time.sleep(0.01)
if a.mode=='descendant':
    subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
outcome='D2_progress_gate_passed' if a.mode=='pass' else 'budget_closed_below_gate'
code=0 if a.mode=='pass' else 2
r=dict(experiment_status='complete',outcome=outcome,progression_gate_passed=a.mode=='pass',
       expected_exit_code=code,teacher_qualified=False,training_parent_eligible=False)
(a.output/'long-worker-result.json').write_text(json.dumps(r))
(a.output/'fake-artifact.txt').write_text('synthetic-only\n')
print('fixture stdout closed before manifest')
raise SystemExit(1 if a.mode=='wrong-exit' else code)
