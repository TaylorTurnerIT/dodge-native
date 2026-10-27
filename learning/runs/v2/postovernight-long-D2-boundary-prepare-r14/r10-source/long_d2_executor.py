#!/usr/bin/env python3
"""Single-use stdlib outer authority. Preparation/preflight never launches ML.

Acceptance requires this receipt PLUS parent-observed outer raw exit and wall.
No production budget, seed, device, retry, resume or campaign override exists.
"""
import time
T0 = time.monotonic()  # First clock, before ordinary imports, never reset.
import argparse
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import traceback
import long_d2 as c
import lifecycle as life
import processes as owned
import boundary_integrity as integrity

NORMAL_SECONDS=7200
REGISTRATION_PATH=c.ORIGINAL_ROOT/c.PREPARE_REL/'registration.json'
LIMITATIONS=[
    'Direct legitimate SIGINT/SIGTERM after a finite pending scan can remain unobserved before _exit.',
    'Transient lease/input changes between samples and changes after the final finite filesystem read are not guaranteed observable.',
    'Kernel uninterruptibility and OS scheduling can exceed a bound; raw/wall/unproven cleanup then reject.',
    'Synthetic stdlib evidence does not qualify teacher, ML runtime, performance or future artifact volume.'
]


def worker_command(controller, output, state, t0, supervisor, gate_fd, executor):
    return [sys.executable,'-B',str(controller),'worker','--output',str(output),
            '--state-path',str(state),'--started',str(t0),'--supervisor-pid',str(supervisor),
            '--executor-fd',str(gate_fd),'--executor-pid',str(executor)]


def checked_registration(path, root):
    c.require(path.resolve()==REGISTRATION_PATH, 'Noncanonical external registration')
    value=c.read_json(path)
    expected={'schema','capsule_path','pins','controller','executor','output','receipt','state_path',
              'protocol_sha256','config_sha256','identity_sha256','capsule_manifest_sha256',
              'classification_sha256','reservation_sha256','class_manifest_hashes','class_counts','cache_policy','root_exclusions'}
    c.require(set(value)==expected and value['schema']=='long_d2_executor_registration_v2', 'Registration schema/key set differs')
    c.require(value['capsule_path']==str(root) and value['controller']==str(root/c.PREPARE_REL/'long_d2.py')
              and value['executor']==str(Path(__file__).resolve())
              and value['output']==str(c.ORIGINAL_ROOT/c.registered_protocol(root/c.PROTOCOL_REL)['output'])
              and value['state_path']==str(c.STATE_PATH), 'Registration paths differ')
    p=c.registered_protocol(root/c.PROTOCOL_REL)
    c.require(value['receipt']==str(c.ORIGINAL_ROOT/p['terminal_lifecycle']['acceptance_receipt'])
              and value['protocol_sha256']==c.PROTOCOL_SHA256 and value['config_sha256']==c.CONFIG_SHA256,
              'Registration protocol/config/receipt differs')
    # Exact pin set; no registration self-hash and no manifest/identity cycle.
    expected_paths={str(root/c.PREPARE_REL/'long_d2.py'),str(root/c.PREPARE_REL/'long_d2_executor.py'),
                    str(root/c.PREPARE_REL/'long-identity.json'),str(root/'capsule-manifest.json'),
                    str(root/c.PROTOCOL_REL),str(root/p['config_path']),
                    str(root/c.PREPARE_REL/'classification.json')}
    c.require(set(value['pins'])==expected_paths, 'External registration pin inventory differs')
    c.verify_files(value['pins'])
    c.require(value['pins'][str(root/c.PREPARE_REL/'long-identity.json')]==value['identity_sha256']
              and value['pins'][str(root/'capsule-manifest.json')]==value['capsule_manifest_sha256'],
              'External raw identity/capsule binding differs')
    return value


def validate_artifacts(output, raw, context, authority):
    p,config,base,identity,pins,lease=context
    authority(True)
    c.require(not output.is_symlink() and output.resolve()==output, 'Escaped output root')
    manifest_path=output/'artifact-manifest.json';terminal_path=output/'finalization-result.json'
    manifest=c.read_json(manifest_path)
    actual=set()
    for path in output.rglob('*'):
        authority(False)
        c.require(not path.is_symlink() and path.resolve().is_relative_to(output), 'Output symlink/escape')
        if path.is_file():
            name=str(path.relative_to(output));actual.add(name)
            c.require('/' not in name and not name.startswith('.') and 'pending' not in name
                      and 'failed-publication' not in name, 'Pending/escaped/failed publication')
    c.require(actual==set(manifest)|{'artifact-manifest.json','finalization-result.json'}, 'Output inventory differs')
    fixed={'long-worker-result.json','long-run-result.json','worker.stdout.log','worker.stderr.log',
           'supervisor-guard.jsonl','worker-resources.jsonl','training-episodes.jsonl','training-metrics.jsonl',
           'entry-restoration.json','entry-control.json','parent-lineage.json','actual-import-origins.json',
           'long-config.json','long-identity.json','checkpoint-index.json','schedule.jsonl'}
    c.require(fixed<=set(manifest), 'Required output evidence missing')
    checkpoint_pattern=r'checkpoint-[0-9]{6}-(?:long_evaluated|long_periodic|long_closure_unevaluated)\.pt(?:\.long-evaluation\.json|\.D2-development\.jsonl)?'
    for name,digest in manifest.items():
        c.require(name in fixed or name in {'worker-verification.jsonl','worker-verification.manifest.json'} or re.fullmatch(checkpoint_pattern,name), 'Unexpected output artifact: '+name)
        authority(False)
        c.require(c.sha(c.safe_member(output,name))==digest, 'Output artifact hash differs: '+name)
        authority(False)
    run=c.read_json(output/'long-run-result.json');terminal=c.read_json(terminal_path)
    wr=c.read_json(output/'long-worker-result.json')
    for item in (run,terminal,wr):
        c.require(c.result_code(item)==raw and item.get('expected_exit_code')==raw
                  and item.get('teacher_qualified') is False and item.get('training_parent_eligible') is False,
                  'Raw/outcome/eligibility binding differs')
        c.require(item.get('B_E_student_D3_opened') is False and item.get('automatic_retries')==0
                  and item.get('same_phase_resume') is False, 'Forbidden phase/retry/resume field')
    for item in (run,terminal):
        c.require(item.get('authoritative') is False and item.get('acceptance_authority')=='outer-executor-receipt'
                  and item.get('internal_decision')=='complete_pending_outer_acceptance', 'Inner authority metadata differs')
    c.require(run['worker_result']==wr and run['worker_exit_code']==raw, 'Worker/run binding differs')
    c.require(terminal['run_result_sha256']==c.sha(output/'long-run-result.json')
              and terminal['artifact_manifest_sha256']==c.sha(manifest_path), 'Terminal/manifest/run binding differs')
    c.require(terminal.get('owned_guard_handles_absent') is True and terminal.get('owned_writers_absent') is True
              and terminal.get('stable_owned_group') is True, 'Owned handles/writers absence missing')
    c.require(wr['run_id']==p['run_id'] and wr['protocol_sha256']==c.PROTOCOL_SHA256
              and wr['config_document_sha256']==c.CONFIG_SHA256
              and wr['identity_document_sha256']==lease['identity_sha256']
              and wr['checkpoint_identity_semantic_sha256']==c.semantic_hash(identity), 'Worker frozen identity differs')
    c.require(c.read_json(output/'long-config.json')==config and c.read_json(output/'long-identity.json')==identity,
              'Output config/identity differs')
    entry=c.read_json(output/'entry-control.json')
    c.require(entry.get('matched') is True and entry.get('rows')==64 and entry.get('fields')==list(c.ROW_KEYS)
              and entry.get('control_document_sha256')==p['entry_control_sha256']
              and all(entry.get(k) is True for k in ('RNG_unchanged','model_Adam_unchanged','zero_gradients_before_control')),
              'Entry control proof differs')
    restoration=c.read_json(output/'entry-restoration.json')
    c.require(restoration.get('matched') is True and restoration.get('before_any_environment_or_gradient') is True
              and set(restoration.get('bitwise_sha256',{}))=={'model','Adam','RNG'}, 'Restoration proof differs')
    lineage=c.read_json(output/'parent-lineage.json')
    c.require(lineage.get('parent_checkpoint_sha256')==p['parent_checkpoint_sha256']
              and lineage.get('parent_terminal_receipt')==p['parent_terminal_receipt']
              and lineage.get('inherited_counters')==c.PARENT_COUNTERS
              and lineage.get('failed_D2_experience_inherited') is False, 'D1 lineage differs')
    origins=c.read_json(output/'actual-import-origins.json')
    c.require(origins==wr['actual_import_origins'] and origins, 'Worker origins evidence missing/different')
    for name,record in origins.items():
        c.require(name=='dodge_rl' or name.startswith('dodge_rl.'), 'Unexpected origin namespace')
        policy=identity['legacy_module_origins'].get(record['origin'])
        c.require(policy is not None and policy['sha256']==record['sha256'] and policy['mirror']==record['mirror'],
                  'Worker origin policy differs')
    final=wr['final_checkpoint'];index=c.read_json(output/'checkpoint-index.json')
    c.require(final in index and final.get('complete_update') is True and final.get('training_parent_eligible') is False
              and final['sha256']==manifest.get(final['checkpoint']), 'Final checkpoint/index binding differs')
    for record in index:
        c.require(record.get('complete_update') is True and record.get('training_parent_eligible') is False
                  and record['sha256']==manifest.get(record['checkpoint']), 'Checkpoint index artifact differs')
        if record.get('evaluated'):
            name=record['checkpoint']+'.long-evaluation.json'
            c.require(record['evaluation_sha256']==manifest.get(name), 'Checkpoint evaluation hash differs')
            cert=c.read_json(output/name);evaluation=cert['evaluations']['D2']
            rows=evaluation['rows']
            c.require(len(rows)==64 and {row['seed'] for row in rows}==set(c.SEEDS)
                      and evaluation['complete'] is True and evaluation['episodes']==64
                      and evaluation['stage']=='D2' and evaluation['action_mode']=='deterministic_argmax'
                      and evaluation['gradients'] is False, 'Evaluation contract differs')
            for row in rows:
                c.require(set(row)==set(c.ROW_KEYS) and row['seed']==c.SEEDS[row['episode_index']], 'Evaluation row differs')
            score=sum(row['score'] for row in rows)/64;alive=sum(row['alive_frames'] for row in rows)/64
            passed=score>=50 and alive>=3060
            c.require(score==evaluation['mean_score'] and alive==evaluation['mean_alive_frames']
                      and cert['checkpoint_sha256']==record['sha256'] and cert['complete'] is True
                      and cert['phase']=='long_D2' and cert['evaluation_stage']=='D2'
                      and cert['teacher_qualified'] is False and cert['training_parent_eligible'] is False
                      and cert['progression_gate_passed']==record['progression_gate_passed']==passed,
                      'Evaluation gate/checkpoint binding differs')
    c.require((raw!=0 or final.get('evaluated') is True and final.get('progression_gate_passed') is True)
              and (raw!=2 or final.get('progression_gate_passed') is False), 'Final gate/raw binding differs')
    for resources in (wr['worker_resources'],terminal['supervisor_resources_final']):
        c.require(resources.get('latched_failure') is None, 'Latched resource/pin failure')
        for key in ('maximum_rss_bytes','maximum_self_peak_rss_bytes','maximum_mps_driver_bytes'):
            c.require(type(resources.get(key)) is int and 0<=resources[key]<=c.LIMIT, 'Resource cap/observation invalid')
        c.require(0<=resources['maximum_sample_gap_seconds']<=.5, 'Safety observation gap invalid')
    c.require(wr.get('integrity_summary') is not None, 'Mandatory worker integrity summary missing')
    authority(True)
    return dict(worker_integrity_summary=wr['integrity_summary'],artifact_manifest_sha256=c.sha(manifest_path),run_result_sha256=c.sha(output/'long-run-result.json'),
                terminal_sha256=c.sha(terminal_path),worker_result_sha256=c.sha(output/'long-worker-result.json'),
                artifacts=manifest, final_checkpoint=final, outcome=wr['outcome'])


class Execution:
    def __init__(self,t0,registration,context,*,supervisor_factory=None,worker_factory=None,guard_factory=c.Guard):
        self.t0,self.registration,self.context=t0,registration,context
        self.pool=life.FailurePool(t0,NORMAL_SECONDS)
        life.POOL=self.pool
        self.latch=life.ProcessLatch();self.latch.install(t0+NORMAL_SECONDS)
        self.supervisor_factory,self.worker_factory=supervisor_factory,worker_factory
        self.guard_factory=guard_factory
        self.groups={};self.child=None;self.worker_wait=None;self.inner_ready=None;self.worker_ready=None
        self.forwarded=[];self.events=[];self.stop=threading.Event();self.watchdog=None
        self.super_channel=self.worker_channel=None
        self.recovery_proven=False;self.cleanup_complete=False
        self.guard=None;self.closed=False
        self.ipc_lock=threading.RLock()

    def fail(self,error,at=None):
        if not isinstance(error,BaseException):
            error=c.Stop(str(error),'safety_stop')
        existing=getattr(error,'first_failure_descriptor',None)
        if existing is not None and at is not None:
            c.require(existing.get('timestamp')==at,'Failure descriptor timestamp differs')
        if at is not None and existing is None:
            error.first_failure_descriptor=dict(timestamp=at,kind='peer_or_source_failure',
                outcome=c.failure_outcome(error),role='outer',timing_basis='explicit_source_timestamp',signal=None)
        primary,descriptor=c.observed_failure(error,self.guard,'outer')
        self.pool.fail(primary,descriptor['timestamp'],descriptor)
        self.latch.phase='FAILURE'

    def authority(self,force=False):
        if self.pool.until is not None:
            raise c.Stop('Executor failure latched: '+str(self.pool.reason))
        self.latch.check()
        self.guard.check()
        c.assert_lease(self.registration['state_path'],self.context[-1])
        if force:self.guard.full_check(True)
        self.guard.sample(full=False)
        self.latch.check()
        c.assert_lease(self.registration['state_path'],self.context[-1])
        c.require(time.monotonic()-self.guard.last_sample<=.5, 'Outer safety observation age exceeded')
        if self.pool.until is not None:raise c.Stop('Executor watchdog failure latched')

    def raw_inner_failure(self, report):
        if report['returncode'] in (0,2):
            return None
        # This is the retained successful direct waitpid observation, not the
        # process exit time and not this later handler's construction time.
        owned.validate_report(report, self.child.process.pid, os.getpid(), self.t0,
                              time.monotonic())
        c.require(report is self.child.report, 'Inner raw report is not retained direct observation')
        error=c.Stop('Inner raw failure','publication_failure')
        error.first_failure_descriptor=dict(timestamp=report['observed_monotonic'],
            kind='direct_wait_observation', outcome='publication_failure', role='outer',
            timing_basis='successful_direct_waitpid_observation', signal=None,
            pid=report['pid'], reaped_by=report['reaped_by'])
        return error

    def monitor_duty(self, name, action):
        """A fallible duty cannot suppress its independent peers or deadline check."""
        try:
            action()
        except BaseException as error:
            # Fixed-size, deduplicated diagnostics. Recording errors never recurses.
            errors=[x for x in self.events if x.get('kind')=='monitor_error']
            detail=repr(error)[:512]
            if len(errors)<8 and not any(x['duty']==name and x['error']==detail for x in errors):
                self.events.append(dict(kind='monitor_error',duty=name,error=detail))
            try:self.fail(error)  # Late earlier source evidence still tightens the pool.
            except BaseException as recording_error:
                errors=[x for x in self.events if x.get('kind')=='monitor_error']
                if len(errors)<8 and not any(x['duty']=='failure_recording' for x in errors):
                    self.events.append(dict(kind='monitor_error',duty='failure_recording',error=repr(recording_error)[:512]))

    def monitor(self):
        # Bind this watchdog's stop request. A failure during normal join must
        # not revive a retiring watchdog or inherit its requested stop.
        stop=self.stop
        while not stop.wait(.02):
            # Outside every fallible duty: persistent IPC/cleanup errors cannot
            # hide the existing absolute failure-only exit bound.
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)
            def cancellation():
                if self.latch.cancellation_requests:
                    number=self.latch.requested_signal
                    if not self.forwarded:
                        self.forwarded.append(dict(signal=int(number),recorded_monotonic=time.monotonic(),
                                                   record_precedes_forward=True))
                        self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_cancel_at)
                        for role,record in tuple(self.groups.items()):
                            def forward(record=record):
                                if number==signal.SIGTERM:owned.signal_once(record,number)
                                else:
                                    try:os.killpg(record['pgid'],number)
                                    except ProcessLookupError:pass
                            self.monitor_duty('cancel_forward_'+role,forward)
                    else:
                        self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_cancel_at)
            self.monitor_duty('cancellation',cancellation)
            def latch_sources():
                if self.latch.first_alarm_at is not None:
                    self.fail(c.Stop('Lifetime wall alarm','wall_guard'),self.latch.first_alarm_at)
                if self.latch.deadline is not None and time.monotonic()>=self.latch.deadline:
                    self.fail(c.Stop('Absolute wall deadline','wall_guard'),self.latch.deadline)
            self.monitor_duty('latch_sources',latch_sources)
            self.monitor_duty('guard_failure',lambda:self.fail(self.guard.failure,self.guard.failure_at)
                              if self.guard is not None and self.guard.failure is not None else None)
            now=time.monotonic()
            for name,condition,at in (
                    ('Worker cutoff',now>=self.t0+c.WORKER_SECONDS and self.worker_wait is None,self.t0+c.WORKER_SECONDS),
                    ('Inner cutoff',now>=self.t0+c.INNER_SECONDS and (self.child is None or self.child.report is None),self.t0+c.INNER_SECONDS),
                    ('Outer cutoff',now>=self.t0+NORMAL_SECONDS,self.t0+NORMAL_SECONDS)):
                if condition:self.monitor_duty(name,lambda name=name,at=at:self.fail(c.Stop(name,'wall_guard'),at))
            self.monitor_duty('sample_age',lambda:self.fail(c.Stop('Outer sample age','resource_stop'))
                              if self.guard is not None and time.monotonic()-self.guard.last_sample>.5 else None)
            def direct_reap():
                report=self.child.poll() if self.child is not None else None
                if report is not None:
                    error=self.raw_inner_failure(report)
                    if error is not None:self.fail(error)
            self.monitor_duty('direct_reap',direct_reap)
            if self.pool.until is not None:
                for role,record in tuple(self.groups.items()):
                    self.monitor_duty('TERM_'+role,lambda record=record:owned.signal_once(record,signal.SIGTERM))
                    if time.monotonic()>=min(self.pool.first+5,self.pool.until-.5):
                        self.monitor_duty('KILL_'+role,lambda record=record:owned.signal_once(record,signal.SIGKILL))
                    def absence(record=record):
                        record['group_absent']=owned.absent(record['pgid'],self.pool.until)
                    self.monitor_duty('absence_'+role,absence)
                self.monitor_duty('cleanup_complete',lambda:setattr(self,'cleanup_complete',
                    self.recovery_proven and self.child is not None and self.child.report is not None
                    and all(r['group_absent'] for r in self.groups.values())))
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)
            def ipc():
                if self.super_channel is not None and self.super_channel.sock.fileno()>=0:
                    with self.ipc_lock:self.pump()
            self.monitor_duty('IPC',ipc)
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)

    def pump(self, deadline_limit=None):
        deadline=min(self.pool.until or self.t0+c.INNER_SECONDS,
                     deadline_limit if deadline_limit is not None else math.inf)
        life.remaining(deadline)
        channels=[x for x in (self.super_channel,self.worker_channel) if x is not None and not getattr(x,'peer_closed',False)]
        readable,_,_=select.select([x.sock for x in channels],[],[],life.remaining(deadline,.005))
        for channel in channels:
            if channel.sock not in readable:continue
            deadline=min(self.pool.until or self.t0+c.INNER_SECONDS,
                         deadline_limit if deadline_limit is not None else math.inf)
            life.remaining(deadline)
            try:
                value,fds=channel.receive(deadline)
            except ConnectionResetError as receive_error:
                expected_close=(self.inner_ready is not None if channel is self.super_channel else self.groups.get('worker',{}).get('done'))
                c.require(expected_close, 'Unexpected private IPC loss: '+json.dumps(getattr(receive_error,'ipc_receive_diagnostic',{}),sort_keys=True))
                channel.peer_closed=True
                continue
            c.require(not fds,'Unexpected IPC FD')
            c.require(value.get('t0_monotonic_hex')==self.t0.hex(), 'Owned IPC clock differs')
            sender=value.get('sender');kind=value.get('kind')
            if kind=='register_worker':
                c.require(channel is self.super_channel and sender==self.child.process.pid and 'worker' not in self.groups,
                          'Wrong/duplicate worker registration')
                pid=value['worker_pid'];command=value['command']
                expected=(worker_command(self.registration['controller'],Path(self.registration['output']),
                          Path(self.registration['state_path']),self.t0,sender,int(command[-3]),os.getpid())
                          if self.worker_factory is None else self.worker_factory(sender,int(command[-3]),self.t0))
                c.require(command==expected and value['worker_pgid']==pid,'Exact worker invocation differs')
                self.groups['worker']=owned.verify_session(pid,sender,command,deadline)
                self.groups['worker'].update(gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)
                self.super_channel.send(dict(kind='registered',worker_pid=pid,t0_monotonic_hex=self.t0.hex()),deadline)
            elif kind=='worker_ready':
                c.require(channel is self.worker_channel,'Worker gate endpoint differs')
                self.worker_ready=value
            elif kind=='failure':
                expected_pid=self.child.process.pid if channel is self.super_channel else self.groups.get('worker',{}).get('pid')
                c.require(sender==expected_pid,'Failure sender ownership missing')
                first=float.fromhex(value['first_monotonic_hex'])
                self.pool.fail(value['reason'],first,value.get('descriptor'),peer=True)
                self.latch.phase='FAILURE'
                channel.send(dict(kind='failure_ack',first_monotonic_hex=self.pool.first.hex(),
                    cleanup_until_monotonic_hex=self.pool.until.hex(),t0_monotonic_hex=self.t0.hex(),descriptor=self.pool.first_global),
                    min(self.pool.until if deadline_limit is None else self.pool.until-.25,deadline))
            elif kind=='worker_done':
                c.require(channel is self.worker_channel and sender==self.groups.get('worker',{}).get('pid'), 'Worker close sender differs')
                self.groups['worker']['done']=True
            elif kind=='worker_wait':
                report=value['report'];worker=self.groups.get('worker',{})
                c.require(channel is self.super_channel and sender==self.child.process.pid and self.worker_wait is None
                          and report['pid']==worker.get('pid') and report['reaped_by']==sender
                          and report['direct_child_reaped'] is True
                          and os.waitstatus_to_exitcode(report['raw_wait_status'])==report['returncode']
                          and self.t0<=report['observed_monotonic']<=time.monotonic(), 'Invalid direct-parent worker wait report')
                owned.validate_report(report,worker.get('pid'),sender,self.t0,time.monotonic(),
                                      before=self.pool.until or self.t0+c.WORKER_SECONDS)
                self.worker_wait=report
                error=c.worker_raw_failure(report,worker.get('pid'),sender,self.t0,'outer')
                if error is not None:self.fail(error)  # Before the next packet or ACK IO.
            elif kind=='inner_ready':
                c.require(channel is self.super_channel and sender==self.child.process.pid,'Inner ready sender differs')
                self.inner_ready=value
            else:raise c.Stop('Unknown owned IPC kind')
        if self.worker_ready is not None and 'worker' in self.groups and not self.groups['worker'].get('gate_ack_attempted',False):
            ready=self.worker_ready;worker=self.groups['worker']
            c.require(ready['sender']==worker['pid'] and ready['supervisor_pid']==self.child.process.pid
                      and ready['executor_pid']==os.getpid() and ready['protocol_sha256']==c.PROTOCOL_SHA256,
                      'Directed worker gate identity differs')
            worker['gate_ack_attempted']=True  # One attempt, including a failed send.
            worker['gate_acked']=False
            try:
                self.worker_channel.send(dict(kind='start_ack',worker_pid=worker['pid'],
                    t0_monotonic_hex=self.t0.hex(),protocol_sha256=c.PROTOCOL_SHA256,
                    identity_sha256=self.registration['identity_sha256'],
                    capsule_manifest_sha256=self.registration['capsule_manifest_sha256']),deadline)
            except BaseException as error:
                worker['gate_ack_failed']=True
                self.fail(error)  # Failure latched before any later channel retirement.
                raise
            worker['gate_acked']=True
            worker['gate_ack_failed']=False
            self.recovery_proven=True

    def recover_registration_race(self,deadline=None):
        if self.child is None:return
        deadline=self.pool.until if deadline is None else deadline
        rows=owned.census(deadline)
        if 'supervisor' not in self.groups and self.child.report is None:
            self.groups['supervisor']=owned.verify_session(self.child.process.pid,os.getpid(),self.supervisor_command,deadline)
        candidates=[]
        for row in rows:
            command=row['argv']
            if (len(command)==16 and command[:4]==[sys.executable,'-B',self.registration['controller'],'worker']
                and command[4:14]==['--output',self.registration['output'],'--state-path',self.registration['state_path'],
                    '--started',str(self.t0),'--supervisor-pid',str(self.child.process.pid),'--executor-fd',command[13]]
                and command[-2:]==['--executor-pid',str(os.getpid())]):
                candidates.append(row)
        # Unknown processes are never signaled. A census cannot prove direct reaping.
        for row in candidates:
            if 'worker' not in self.groups:
                self.groups['worker']=owned.verify_session(row['pid'],self.child.process.pid,row['argv'],deadline,orphan=True)
        self.recovery_proven=True
        self.events.append(dict(kind='bounded_registration_census',matches=len(candidates),
                                worker_reaping_claimed=False,monotonic=time.monotonic()))

    def publish_failed(self,receipt_path,error):
        """Reserve the final .25s of the same pool for a mandatory attempt.

        The watchdog keeps killing/probing owned groups through the unchanged
        absolute deadline. An unproven cleanup cannot cause an early exit.
        """
        cleanup_errors=[]
        try:
            if self.child is not None:self.recover_registration_race(self.pool.until-.25)
            else:self.recovery_proven=True;self.cleanup_complete=True
        except BaseException as cleanup_error:
            cleanup_errors.append(repr(cleanup_error))
        while not self.cleanup_complete and time.monotonic()<self.pool.until-.25:
            try:
                with self.ipc_lock:self.pump()
            except BaseException as cleanup_error:
                if len(cleanup_errors)<8:cleanup_errors.append(repr(cleanup_error))
            time.sleep(max(0,min(.02,self.pool.until-.25-time.monotonic())))
        # Finite best-effort drain inside the existing publication reserve.
        # No promise that queued datagrams will arrive or be schedulable here.
        for _ in range(4):
            try:
                with self.ipc_lock:
                    life.remaining(self.pool.until-.25)
                    self.pump(deadline_limit=self.pool.until-.25)
            except BaseException as cleanup_error:
                if len(cleanup_errors)<8:cleanup_errors.append(repr(cleanup_error))
        reaping={}
        for role,report,parent in (
                ('supervisor',None if self.child is None else self.child.report,os.getpid()),
                ('worker',self.worker_wait,self.groups.get('supervisor',{}).get('pid'))):
            status='unproven' if role in self.groups else 'not_registered'
            basis='direct_wait_report_missing'
            if report is not None:
                try:
                    owned.validate_report(report,self.groups[role]['pid'],parent,self.t0,
                                          time.monotonic(),before=self.pool.until)
                    if role=='supervisor':
                        c.require(report is self.child.report and report['pid']==self.child.process.pid,
                                  'Supervisor direct observation source differs')
                    status='direct_reaped';basis='validated_direct_parent_waitpid_report'
                except BaseException as report_error:
                    if len(cleanup_errors)<8:cleanup_errors.append(repr(report_error))
            elif role=='worker' and self.child is not None and self.child.report is not None:
                basis='supervisor_dead_before_report'
            reaping[role]=dict(status=status,basis=basis)
        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False,
            experiment_status='failed' if self.cleanup_complete else 'failed_partial',expected_exit_code=1,
            error=self.pool.reason,trigger_error=repr(error),traceback=traceback.format_exc(),
            executor_t0_monotonic=self.t0,
            first_failure_monotonic=self.pool.first,cleanup_until_monotonic=self.pool.until,
            cleanup_complete=self.cleanup_complete,recovery_proven=self.recovery_proven,reaping=reaping,
            cleanup_errors=cleanup_errors,first_local_failure=self.pool.first_local,
            first_global_failure=self.pool.first_global,ownership=self.groups,
            inner_wait=None if self.child is None else self.child.report,
            worker_wait=self.worker_wait,forwarded_cancellation=self.forwarded,events=self.events,
            teacher_qualified=False,training_parent_eligible=False,limitations=LIMITATIONS)
        try:
            receipt_path.parent.mkdir(parents=False,exist_ok=True)
            c.mandatory_failure(receipt_path,result,self.pool.until)
        except BaseException as publication_error:
            result['mandatory_failure_publication_error']=repr(publication_error)
        # Optional IO and joins run only after positive absence. If survivors
        # remain, leave the watchdog active and spend no extra cleanup allowance.
        while not self.cleanup_complete:
            life.remaining(self.pool.until)
            try:
                with self.ipc_lock:self.pump()
            except BaseException:pass
            time.sleep(life.remaining(self.pool.until,.02))
        try:
            if self.guard is not None:
                self.guard.event.set()
                for thread in (self.guard.thread,self.guard.verify_thread):
                    if thread is not None:thread.join(timeout=life.remaining(self.pool.until,.5))
        except BaseException:pass
        try:
            c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',self.pool.until) if self.guard is not None else None
        except BaseException:pass
        self.stop.set()
        try:self.watchdog.join(timeout=life.remaining(self.pool.until,.5))
        except BaseException:pass
        for channel in (self.super_channel,self.worker_channel):
            try:
                if channel is not None:channel.sock.close()
            except BaseException:pass
        return result

    def run(self):
        receipt_path=Path(self.registration['receipt'])
        result=None;code=1
        try:
            p,config,base,identity,pins,lease=self.context
            c.assert_lease(self.registration['state_path'],lease)
            c.require(not receipt_path.exists() and not Path(self.registration['output']).exists(), 'Single-use output/receipt already exists')
            def verify():
                c.verify_files(self.registration['pins'])
                c.require(c.sha(REGISTRATION_PATH)==self.registration_digest, 'External registration changed')
                integrity.cache_check(self.registration['cache_policy'])
                return integrity.verify(self.context,c.ROOT)
            self.guard=self.guard_factory(self.t0+NORMAL_SECONDS,
                lambda:c.assert_lease(self.registration['state_path'],lease),verify,None)
            self.registration_digest=c.sha(REGISTRATION_PATH)
            self.guard.start()
            self.watchdog=threading.Thread(target=self.monitor,name='long-D2-executor-watchdog',daemon=True)
            life.start_thread(self.watchdog)
            self.preflight=integrity.verify(self.context,c.ROOT,endpoint='preflight')
            self.authority(False)
            parent,child_socket=life.pair();gate_parent,gate_child=life.pair()
            self.super_channel=life.Channel(parent);self.worker_channel=life.Channel(gate_parent)
            command=([sys.executable,'-B',self.registration['controller'],'run','--output',self.registration['output'],
                      '--state-path',self.registration['state_path'],'--executor-fd',str(child_socket.fileno()),
                      '--executor-pid',str(os.getpid())] if self.supervisor_factory is None
                     else self.supervisor_factory(child_socket.fileno(),self.t0))
            self.supervisor_command=command
            mask=signal.pthread_sigmask(signal.SIG_BLOCK,life.OWNED)
            try:
                process=subprocess.Popen(command,cwd=c.ROOT,start_new_session=True,pass_fds=(child_socket.fileno(),),
                                         env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
                self.child=owned.Child(process)
                # Supervisor is blocked waiting on this endpoint, so command census is stable.
                self.groups['supervisor']=owned.verify_session(process.pid,os.getpid(),command,self.t0+c.INNER_SECONDS)
                self.super_channel.send(dict(kind='start',clock_schema='long_d2_owned_start_v1',executor_pid=os.getpid(),
                    t0_monotonic_hex=self.t0.hex(),protocol_sha256=c.PROTOCOL_SHA256,
                    identity_sha256=self.registration['identity_sha256'],
                    capsule_manifest_sha256=self.registration['capsule_manifest_sha256']),self.t0+c.INNER_SECONDS,gate_child.fileno())
                child_socket.close();gate_child.close()
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,mask)
            self.guard.rss=lambda:max(c.sampled_rss(os.getpid()),owned.group_rss([r['pgid'] for r in tuple(self.groups.values())],self.pool.until or self.t0+NORMAL_SECONDS))
            while self.child.poll() is None:
                with self.ipc_lock:self.pump()
                self.authority(False)
            inner=self.child.report
            error=self.raw_inner_failure(inner)
            if error is not None:raise error  # Preserve source time before any terminal IO/drain.
            for _ in range(4):
                with self.ipc_lock:self.pump()  # Finite drain of bounded terminal records.
            c.require(inner['returncode'] in (0,2) and inner['observed_monotonic']<self.t0+c.INNER_SECONDS,
                      'Inner raw exit/wall invalid')
            c.require(self.worker_wait is not None and self.worker_wait['returncode']==inner['returncode']
                      and self.worker_wait['observed_monotonic']<self.t0+c.WORKER_SECONDS,
                      'Normal worker reaping/raw/deadline proof missing')
            c.require(self.inner_ready is not None and self.inner_ready['expected_exit_code']==inner['returncode']
                      and self.inner_ready['owned_guard_handles_absent'] is True
                      and self.inner_ready['owned_writers_absent'] is True, 'Inner handles/writers proof missing')
            for record in self.groups.values():
                record['group_absent']=owned.absent(record['pgid'],self.t0+NORMAL_SECONDS)
                c.require(record['group_absent'], 'Owned group absence unproven')
            c.require(set(self.groups)=={'supervisor','worker'} and self.groups['worker']['gate_acked'] is True, 'Owned group registration incomplete')
            self.authority(True)
            bindings=validate_artifacts(Path(self.registration['output']),inner['returncode'],self.context,self.authority)
            postflight=integrity.verify(self.context,c.ROOT,endpoint='postflight')
            summary=dict(schema='long_d2_compact_integrity_summary_v1',
                protocol_sha256=c.PROTOCOL_SHA256, config_sha256=c.CONFIG_SHA256,
                identity_sha256=self.registration['identity_sha256'], classification_sha256=self.registration['classification_sha256'],
                reservation_sha256=self.registration['reservation_sha256'], manifests=self.registration['class_manifest_hashes'],
                preflight=self.preflight,postflight=postflight,worker=bindings['worker_integrity_summary'],
                first_local_failure=self.pool.first_local,first_global_failure=self.pool.first_global)
            c.require(integrity.summary_valid(summary,self.registration),'Mandatory integrity summary differs')
            summary_path=receipt_path.parent/'integrity-summary.json'
            receipt_path.parent.mkdir(parents=False,exist_ok=True)
            c.save(summary_path,summary)
            bindings['integrity_summary_sha256']=c.sha(summary_path)
            bindings['integrity_summary_path']=str(summary_path)
            code=inner['returncode']
            result=dict(schema='long_d2_outer_acceptance_v2',accepted=True,experiment_status='complete',
                expected_exit_code=code,outcome=bindings['outcome'],teacher_qualified=False,training_parent_eligible=False,
                authoritative_only_with_parent_observed_raw_exit_and_wall=True,
                t0_monotonic_hex=self.t0.hex(),inner_wait=inner,worker_wait=self.worker_wait,
                ownership=self.groups,forwarded_cancellation=self.forwarded,bindings=bindings,
                registration=self.registration,registration_sha256=self.registration_digest,integrity_summary=summary,required_lease=lease,outer_resources=self.guard.receipt(),
                limitations=LIMITATIONS,receipt_excludes_own_hash=True,
                wall_seconds_lower_bound=time.monotonic()-self.t0)
            receipt_path.parent.mkdir(parents=False,exist_ok=True)
            self.authority(True)
            c.replace_json(receipt_path,result)
            self.authority(True)  # Includes write, flush, fsync, rename and close.
            # Keep the one lifetime alarm interrupting through ALL normal IO,
            # including Guard/watchdog/endpoint teardown and final authority.
            # Only failure handling defers; final_exit blocks without restoring.
            self.guard.close()
            self.authority(False)
            self.stop.set()
            self.watchdog.join(timeout=life.remaining(self.t0+NORMAL_SECONDS,.5))
            c.require(not self.watchdog.is_alive(),'Executor watchdog join unproven')
            self.super_channel.sock.close();self.worker_channel.sock.close()
            def final_hash_observer():
                self.guard.check()
                if time.monotonic()-self.guard.last_sample>=.15:self.guard.sample(full=False)
            c.HASH_OBSERVER=final_hash_observer
            self.authority(True)  # Includes watchdog and endpoint close.
            c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',
                                      self.t0+NORMAL_SECONDS,lambda: self.authority(False))
            self.closed=True
        except BaseException as error:
            self.fail(error)
            if self.stop.is_set() or self.watchdog is None or not self.watchdog.is_alive():
                self.stop=threading.Event()
                self.watchdog=threading.Thread(target=self.monitor,name='long-D2-executor-watchdog',daemon=True)
                life.start_thread(self.watchdog)
            try:self.publish_failed(receipt_path,error)
            except BaseException:pass
            code=1
        deadline=self.pool.until if self.pool.until is not None else self.t0+NORMAL_SECONDS
        life.final_exit(code,self.latch,deadline,lambda:self.pool.until is not None or self.guard is not None and self.guard.failure is not None)


def validate_wait_reports(receipt, raw_exit, elapsed_seconds):
    groups=receipt['ownership']
    c.require(set(groups)=={'supervisor','worker'},'Ownership incomplete')
    t0=float.fromhex(receipt['t0_monotonic_hex'])
    c.require(math.isfinite(t0) and t0>=0,'Invalid T0')
    for role,key,seconds in (('supervisor','inner_wait',c.INNER_SECONDS),('worker','worker_wait',c.WORKER_SECONDS)):
        group=groups[role];report=receipt[key]
        pid=group['pid'];parent=group['parent_at_registration']
        c.require(type(pid) is int and pid>1 and type(parent) is int and parent>1
                  and group['pgid']==pid and group['new_session_verified'] is True
                  and group['group_absent'] is True,'Invalid owned group')
        c.require(type(report['pid']) is int and report['pid']==pid
                  and type(report['reaped_by']) is int and report['reaped_by']==parent
                  and report['direct_child_reaped'] is True,'Direct-parent reap missing')
        status=report['raw_wait_status'];rc=report['returncode'];at=report['observed_monotonic']
        c.require(type(status) is int and 0<=status<=65535 and os.WIFEXITED(status)
                  and type(rc) is int and rc==raw_exit and os.waitstatus_to_exitcode(status)==rc,
                  'Raw wait/outcome differs')
        c.require(type(at) in (int,float) and math.isfinite(at)
                  and t0<=at<t0+seconds and at<=t0+elapsed_seconds,'Direct reap time invalid')
    c.require(groups['worker']['parent_at_registration']==groups['supervisor']['pid']
              and groups['worker']['pid']!=groups['supervisor']['pid']
              and receipt['worker_wait']['observed_monotonic']<=receipt['inner_wait']['observed_monotonic'],
              'Owned parent/order differs')
    return True


def accept_observed(receipt, raw_exit, elapsed_seconds, *, registration_sha256=None, summary_sha256=None):
    """Parent holds these digests and independently observes raw exit and wall.

    File checks are current actual bytes, not a manifest-only passing verdict.
    Missing parent pins, mandatory summary, ownership, or critical files reject.
    """
    try:
        if not (type(raw_exit) is int and raw_exit in (0,2) and type(elapsed_seconds) in (int,float)
                and math.isfinite(elapsed_seconds) and 0<=elapsed_seconds<=NORMAL_SECONDS
                and receipt.get('schema')=='long_d2_outer_acceptance_v2' and receipt.get('accepted') is True
                and receipt.get('expected_exit_code')==raw_exit and receipt.get('experiment_status')=='complete'
                and receipt.get('outcome')==('D2_progress_gate_passed' if raw_exit==0 else 'budget_closed_below_gate')
                and receipt.get('teacher_qualified') is False and receipt.get('training_parent_eligible') is False):
            return False
        registration=receipt['registration'];bindings=receipt['bindings'];summary=receipt['integrity_summary']
        c.require(registration_sha256 is not None and receipt['registration_sha256']==registration_sha256==c.sha(REGISTRATION_PATH), 'Parent registration digest missing/different')
        c.require(c.read_json(REGISTRATION_PATH)==registration,'Registration content differs')
        c.verify_files(registration['pins'])
        c.require(summary_sha256 is not None and bindings['integrity_summary_sha256']==summary_sha256==c.sha(bindings['integrity_summary_path']), 'Parent summary digest missing/different')
        c.require(c.read_json(bindings['integrity_summary_path'])==summary and integrity.summary_valid(summary,registration),'Mandatory summary differs')
        c.require(receipt['required_lease']==c.read_json(c.ORIGINAL_ROOT/c.PREPARE_REL/'required-lease.json'),'Required ownership/lease differs')
        c.require(set(receipt['ownership'])=={'supervisor','worker'} and all(v['new_session_verified'] and v['group_absent'] for v in receipt['ownership'].values()),'Ownership incomplete')
        validate_wait_reports(receipt,raw_exit,elapsed_seconds)
        output=Path(registration['output'])
        c.verify_files({str(output/k):v for k,v in bindings['artifacts'].items()})
        for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
            c.require(c.sha(output/name)==bindings[key],'Critical artifact differs: '+name)
        return True
    except (KeyError, TypeError, ValueError, OverflowError, OSError, c.Stop):
        return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('preflight','run'))
    parser.add_argument('--registration',type=Path,default=REGISTRATION_PATH)
    parser.add_argument('--registration-sha256',required=True)
    args=parser.parse_args()
    c.require(c.sha(args.registration)==args.registration_sha256, 'Parent launch registration digest differs')
    if args.command=='preflight':
        registration=checked_registration(args.registration,c.ROOT)
        result=c.pure_preflight(c.ROOT)
        result.update(executor_registration_verified=True,launch_performed=False)
        print(json.dumps(result,sort_keys=True,indent=2))
        return
    # Timer starts before context hashing. No ML import occurs in this executor.
    execution=Execution(T0,None,None)
    try:
        execution.registration=checked_registration(args.registration,c.ROOT)
        execution.context=c.capsule_context(c.ROOT,verify_inputs=False)
    except BaseException as error:
        execution.fail(error)
        life.final_exit(1,execution.latch,execution.pool.until)
    execution.run()


if __name__=='__main__':main()
