"""Record the read-only follow-up without reopening the consumed experiment."""
from pathlib import Path
import datetime
import hashlib
import json
import os

HERE = Path(__file__).resolve().parent
state = json.loads((HERE/'state.json').read_text())
launch = json.loads((HERE/'postovernight-long-D2-r2-terminal-diagnosis-sonnet-launch.json').read_text())
assert state['active_long_campaign'] is None
assert state['post_overnight_long_D2_r2']['single_use_consumed']
brief = HERE/'postovernight-long-D2-r2-terminal-diagnosis-sonnet-task.md'
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
state['tasks']['postovernight_long_D2_r2_terminal_diagnosis_sonnet'] = dict(
    task_id=launch['taskId'], status=launch['status'], workState=launch['workState'],
    result_ingested=False, registered_at_utc=stamp, planned_budget_seconds=600,
    owned='learning/runs/v2/postovernight-long-D2-r2-terminal-diagnosis-sonnet-r1/',
    task_prompt=brief.name, task_prompt_sha256=hashlib.sha256(brief.read_bytes()).hexdigest(),
    launch_receipt='postovernight-long-D2-r2-terminal-diagnosis-sonnet-launch.json',
    scope='Readonly shutdown/learning diagnosis and next-step proposal; no experiment or source changes.')
state['post_overnight_long_D2_r2'].update(
    terminal_diagnosis_task_id=launch['taskId'],
    terminal_report='docs/v2-long-D2-results-2026-10-25.md')
state.update(status='postovernight_long_D2_r2_closed_failed;readonly_sonnet_diagnosis_running;no_training',
             last_update_at_utc=stamp,
             next_actions=['Ingest the read-only Sonnet diagnosis once and reconcile supported proposals.',
                           'Preserve the failed experiment and all checkpoints; no retry, resume or follow-on training.'])
pending = HERE/'.state-r2-diagnosis.pending.json'
with pending.open('x') as stream:
    json.dump(state, stream, sort_keys=True, indent=2, allow_nan=False)
    stream.write('\n')
os.replace(pending, HERE/'state.json')
print(json.dumps(dict(diagnosis_task=launch['taskId'], lease_cleared=True, training_active=False)))
