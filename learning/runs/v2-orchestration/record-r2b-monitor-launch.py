"""Parent bookkeeping for an already launched, exclusively monitored experiment."""
from pathlib import Path
import datetime
import hashlib
import json
import os

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OBSERVER = ROOT / 'learning/runs/v2/postovernight-long-D2-execution-observer-r2b'
state = json.loads((HERE / 'state.json').read_text())
launch = json.loads((HERE / 'postovernight-long-D2-execution-r2b-monitor-launch.json').read_text())
returned = json.loads((OBSERVER / 'Popen-returned.json').read_text())
before = json.loads((OBSERVER / 'Popen-before.json').read_text())
assert state['post_overnight_long_D2_r2']['single_use_consumed']
assert state['post_overnight_long_D2_r2']['actual_command_launch_count'] == 1
assert returned['pid'] == returned['session'] == 10178
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
brief = HERE / 'postovernight-long-D2-execution-r2b-monitor-task.md'
task = state['tasks']['postovernight_long_D2_execution_r2b']
task.update(task_id=launch['taskId'], status=launch['status'], workState=launch['workState'],
            registered_at_utc=stamp, actual_command_launch_count=1, observer_pid=10177,
            outer_pid=returned['pid'], parent_tool_session=66682,
            task_prompt=brief.name, task_prompt_sha256=hashlib.sha256(brief.read_bytes()).hexdigest(),
            launch_receipt='postovernight-long-D2-execution-r2b-monitor-launch.json',
            scope='Parent-launched pinned observer; child only monitors existing execution and collects terminal evidence in monitor/.')
run = state['post_overnight_long_D2_r2']
run.update(status='running_actual_frozen_command;entry_restoration_and_control_matched',
           execution_task_id=launch['taskId'], execution_monitor_task_id=launch['taskId'],
           original_prelaunch_observer_task_id=state['tasks']['postovernight_long_D2_execution_r2']['task_id'],
           execution_observer=str(OBSERVER.relative_to(ROOT)), observer_pid=10177,
           outer_pid=returned['pid'], execution_shell_session=66682,
           execution_started_at_utc=before['utc'], entry_restoration_matched=True,
           entry_control_rows_matched=64)
state.update(status='postovernight_long_D2_r2_running;one_actual_launch;monitor_attached',
             last_update_at_utc=stamp,
             next_actions=['Leave the one existing observer and monitor running; no replacement launch or source mutation.',
                           'Ingest the monitor terminal result once, audit actual raw/wall/receipts/resources/owned cleanup, then clear only the exact lease.',
                           'No retry, failed-weight resume, extra evaluation, D3, student or follow-on experiment.'])
pending = HERE / '.state-r2b-monitor.pending.json'
with pending.open('x') as stream:
    json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write('\n')
os.replace(pending, HERE / 'state.json')
doc = ROOT / 'docs/v2-long-D2-harness-status-2026-10-25.md'
text = doc.read_text()
old = 'The authorized one-shot 7,200-second D2 execution observer is dispatched; launch checks are underway.'
new = 'The one-shot 7,200-second D2 run started at 05:12:18 UTC. D1 model/Adam/RNG restoration and all 64 entry-control rows matched before gradients; one completion monitor is attached.'
assert text.count(old) == 1
text = text.replace(old, new)
text += '\nThe first execution observer launched no campaign because it checked the D1 row log against the evaluation-certificate hash. Parent verified the correct certificate and zero launches, retained that observer, and launched the corrected external wrapper once; production source and limits stayed unchanged. [Reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-execution-r2-prelaunch-parent-reconciliation.json) · [Corrected observer](../learning/runs/v2/postovernight-long-D2-execution-observer-r2b/).\n'
doc.write_text(text)
print(json.dumps(dict(actual_launches=1, outer_pid=returned['pid'],
                      monitor_task_id=launch['taskId'], lease_retained=state['active_long_campaign'] is not None)))
