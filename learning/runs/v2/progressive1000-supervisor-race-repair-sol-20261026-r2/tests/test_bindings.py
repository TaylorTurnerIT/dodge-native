"""Bounded stdlib controls only. Fixtures are never launch/qualification evidence."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

OWN = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(OWN))
import binding as b
import execute_once as launcher
import observe
import terminal

ASSEMBLY = b.ROOT/'learning/runs/v2/progressive1000-matched-run-parent-assembly-20261026-r1/assembly.json'


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OWN/'tests',prefix='synthetic-')
        self.home = Path(self.temp.name)
        self.reg = b.read(b.read(ASSEMBLY)['runs'][0]['registration_path'])
        self.reg['output'] = str(self.home/'worker-output')
        self.envelope = dict(started=time.monotonic(),registration_sha256='synthetic-registration',
            registration='synthetic-registration-path',launch_approval='synthetic-launch-approval',
            launch_approval_sha256='synthetic-approval-sha',source_acceptance='separate-source-acceptance',
            control=str(self.home/'control'),cancel_path=str(self.home/'cancel'))

    def tearDown(self):
        self.temp.cleanup()

    def test_cli_binds_launch_approval_and_shared_start(self):
        cmd = b.worker_command(self.envelope,self.reg)
        self.assertEqual(cmd[:3],[self.reg['interpreter'],'-B',str(b.SOURCE/'worker_cli.py')])
        flags = dict(zip(cmd[3::2],cmd[4::2]))
        self.assertEqual(set(flags),{'--registration','--registration-sha256','--source-acceptance','--source-acceptance-sha256','--started'})
        self.assertEqual(flags['--source-acceptance'],'synthetic-launch-approval')
        self.assertEqual(float(flags['--started']),self.envelope['started'])

    def test_exact_parent_marker_and_gate_contract(self):
        c = b.contracts(); digest = 'd'*64; approval_sha = 'a'*64; started = time.monotonic()
        approval = dict(schema='progressive1000_parent_launch_approval_v1',status='approved_exactly_one_registered_run',
            registration_sha256=digest,source_manifest_sha256=self.reg['source_manifest_sha256'],
            runtime_manifest_sha256=self.reg['runtime_manifest_sha256'],run_id=self.reg['run_id'],gates=dict.fromkeys(c.GATES,'passed'))
        marker = dict(schema='progressive1000_parent_spent_launch_marker_v1',registration_sha256=digest,run_id=self.reg['run_id'],started=started)
        # These approval/marker objects exist only in this mocked CPU control.
        def read(path): return self.reg if path == 'registration' else approval if path == 'approval' else marker
        with patch.object(c,'sha',side_effect=lambda p:digest if p == 'registration' else approval_sha), patch.object(c,'read',side_effect=read), patch.object(c,'validate_static',return_value={}), patch.object(c,'cache_check'):
            self.assertEqual(c.preflight('registration',digest,'approval',approval_sha,started)[0],self.reg)
            marker['started_monotonic'] = marker.pop('started')
            with self.assertRaisesRegex(ValueError,'parent-spent launch marker differs'):
                c.preflight('registration',digest,'approval',approval_sha,started)
            marker['started'] = marker.pop('started_monotonic'); approval['gates'].pop(c.GATES[-1])
            with self.assertRaisesRegex(ValueError,'later parent gates missing'):
                c.preflight('registration',digest,'approval',approval_sha,started)

    def test_inert_envelope_rejected_without_control_creation(self):
        path = self.home/'inert.json'
        envelope = dict(schema='progressive1000_existing_supervisor_envelope_v1',status='DRAFT_NO_LAUNCH',
            registration='x',registration_sha256='x',launch_approval='x',launch_approval_sha256='x',
            source_acceptance='x',source_acceptance_sha256='x',control=str(self.home/'control'),cancel_path='x',
            started=None,pins={},interpreter_resolved='x',interpreter_sha256='x')
        b.save(path,envelope)
        with self.assertRaisesRegex(ValueError,'inert envelope'):
            observe.main(path,b.sha(path))
        self.assertFalse((self.home/'control').exists())

    def test_sampled_rss_new_field_and_torn_tail(self):
        out = Path(self.reg['output']);out.mkdir()
        (out/'resources.jsonl').write_text('{"rss_bytes":19,"mps_driver_bytes":23}\n{"rss_bytes":999')
        self.assertEqual(b.worker_resources(out),dict(samples=1,peak_rss_bytes=19,peak_mps_driver_bytes=23))
        with self.assertRaisesRegex(ValueError,'torn terminal resource journal'):
            b.worker_resources(out,strict=True)

    def test_failed_worker_preserves_raw_exit_string_and_partial_optimizer(self):
        control = Path(self.envelope['control'])
        out = Path(self.reg['output']);out.mkdir()
        failure = dict(status='failed',first_failure="RuntimeError('original PPO failure')",finalization_error='later cleanup failure',
            final_snapshot=dict(state='failed',completed_optimizer_steps=4,
                actual_optimizer_steps_including_failed_update=7,last_update_progress=dict(optimizer_steps=3,in_update=True,complete=False)))
        b.save(out/'worker-result.json',failure)
        (out/'training-metrics.jsonl').write_text(json.dumps(dict(metrics=dict(optimizer_steps=4)))+'\n')
        class Fake:
            pid = 987654321
            returncode = 7
            def poll(self): return 7
            def wait(self,timeout=None): return 7
        with patch.object(b,'load_envelope',return_value=(self.envelope,self.reg)), patch.object(b,'verify_bound'), patch.object(b,'check_lease'), patch.object(observe,'group_exists',return_value=False), patch.object(observe,'process_rows',return_value={}):
            code = launcher.execute('unused','synthetic',popen=lambda *a,**k:Fake())
            self.assertEqual(code,1)
            with self.assertRaises(FileExistsError): launcher.execute('unused','synthetic',popen=lambda *a,**k:self.fail('retry'))
        receipt = b.read(control/'execution-result.json')
        self.assertEqual(receipt['observed_worker_raw_exit'],7)
        self.assertEqual(receipt['worker_result']['first_failure'],failure['first_failure'])
        self.assertEqual(receipt['terminal_accounting']['actual_optimizer_steps_including_failed_update'],7)
        self.assertEqual(receipt['terminal_accounting']['last_update_progress']['optimizer_steps'],3)
        self.assertIsNone(receipt['terminal_accounting']['initial_startup_frames'])
        self.assertEqual(sorted(p.name for p in out.iterdir()),['training-metrics.jsonl','worker-result.json'])

    def test_cancellation_cleans_exact_owned_group_once(self):
        control = Path(self.envelope['control'])
        class Fake:
            pid = 987654321
            returncode = None
            def poll(self): return self.returncode
            def wait(self,timeout=None): return self.returncode
        process = Fake(); called = []
        def stop(p,**kwargs): called.append(p.pid);p.returncode=-15;return dict(reaped=True,exit_code=-15)
        Path(self.envelope['cancel_path']).touch()
        with patch.object(b,'load_envelope',return_value=(self.envelope,self.reg)), patch.object(b,'verify_bound'), patch.object(observe,'group_exists',return_value=False), patch.object(observe,'process_rows',return_value={}), patch.object(observe,'signal_owned',side_effect=lambda proc,anchors,sig,record:stop(proc)):
            self.assertEqual(launcher.execute('unused','synthetic',popen=lambda *a,**k:process),1)
        receipt = b.read(control/'execution-result.json')
        self.assertEqual(called,[process.pid]);self.assertEqual(receipt['observed_worker_raw_exit'],-15)
        self.assertFalse(Path(self.reg['output']).exists())

    def test_original_cleanup_term_kill_with_fake_process(self):
        class Fake:
            pid = 987654321
            calls = 0
            code = None
            def wait(self,timeout=None):
                self.calls += 1
                if self.calls == 1: raise subprocess.TimeoutExpired('stdlib-fake',timeout)
                self.code = -9
            def poll(self): return self.code
        with patch.object(launcher.os,'killpg') as kill:
            result = launcher.stop_owned(Fake())
        self.assertEqual([c.args for c in kill.call_args_list],[(987654321,signal.SIGTERM),(987654321,signal.SIGKILL)])
        self.assertEqual(result['exit_code'],-9);self.assertTrue(result['reaped'])

    def test_observer_refuses_stale_identity(self):
        row = dict(pid=987654321,pgid=987654321,start_identity='original',command='stdlib-fake')
        current = dict(row,start_identity='reused')
        with patch.object(observe,'process_rows',return_value={row['pid']:current}), patch.object(os,'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError,'identity no longer proven'):
                observe.signal_group(row['pgid'],{row['pid']:row},signal.SIGKILL,dict(cleanup_signals=[]))
            kill.assert_not_called()

    def test_external_watchdog_term_kill_and_raw_exit(self):
        # Fake process table and clock exercise the external monitor, not training.
        self.envelope['started']=0
        class Clock:
            now=1789.0
            def monotonic(self): return self.now
            def sleep(self,seconds): self.now+=1
        clock=Clock()
        class Fake:
            pid=987654321
            returncode=None
            def poll(self): return self.returncode
            def wait(self,timeout=None):
                if self.returncode is None: raise subprocess.TimeoutExpired('stdlib-fake',timeout)
                return self.returncode
        process=Fake()
        row=dict(pid=process.pid,ppid=os.getpid(),pgid=process.pid,rss_bytes=1,start_identity='synthetic',command='stdlib-fake')
        def table(): return {process.pid:row} if process.returncode is None else {}
        signals=[]
        def group(pgid,anchors,sig,record):
            signals.append((pgid,sig))
            record['cleanup_signals'].append(dict(owned_pgid=pgid,signal=signal.Signals(sig).name))
            if sig==signal.SIGKILL:process.returncode=-9
        with patch.object(b,'load_envelope',return_value=(self.envelope,self.reg)), patch.object(b,'verify_bound'), patch.object(b,'check_lease'), patch.object(observe.subprocess,'Popen',return_value=process), patch.object(observe,'process_rows',side_effect=table), patch.object(observe,'signal_owned',side_effect=lambda proc,anchors,sig,record:group(proc.pid,anchors,sig,record)), patch.object(observe,'group_exists',return_value=False), patch.object(observe.time,'monotonic',side_effect=clock.monotonic), patch.object(observe.time,'sleep',side_effect=clock.sleep):
            self.assertEqual(observe.main('unused','synthetic',clock=clock.monotonic,sleep=clock.sleep),1)
        receipt=b.read(Path(self.envelope['control'])/'observation.json')
        self.assertEqual(receipt['first_event']['kind'],'external_work_deadline')
        self.assertEqual(receipt['observed_worker_raw_exit'],-9)
        self.assertEqual(signals,[(process.pid,signal.SIGTERM),(process.pid,signal.SIGKILL)])
        self.assertEqual(receipt['launch_count'],1)
        self.assertLess(receipt['elapsed_seconds'],1800)

    def test_lease_drift_fails_before_worker_dispatch(self):
        control=Path(self.envelope['control'])
        with patch.object(b,'load_envelope',return_value=(self.envelope,self.reg)), patch.object(b,'verify_bound',side_effect=ValueError('parent lease changed')):
            self.assertEqual(launcher.execute('unused','synthetic',popen=lambda *a,**k:self.fail('unauthorized dispatch')),1)
        self.assertTrue((control/'supervisor.claimed').is_file())
        self.assertFalse(Path(self.reg['output']).exists())
        receipt=b.read(control/'observation.json')
        self.assertIsNone(receipt['worker_group_absent'])
        self.assertEqual(receipt['worker_ownership_state'],'not_launched')

    def test_completed_global60_json_and_hash_binding(self):
        worker = self.completed_fixture()
        report = terminal.validate_outputs(self.reg,worker,self.envelope['registration_sha256'])
        self.assertEqual(report['completed_updates_journaled'],60)
        self.assertEqual(report['returned_environment_decisions'],983040)
        self.assertEqual(report['completed_optimizer_steps_journaled'],60)
        self.assertEqual(report['integrity_files_checked'],5)
        self.assertEqual(report['ordinary_caps'],192)
        bad = copy.deepcopy(worker);bad['integrity_checkpoints'][-1]['phase_update']=432
        with self.assertRaisesRegex(ValueError,'integrity file/sidecar identity differs'):
            terminal.validate_outputs(self.reg,bad,self.envelope['registration_sha256'])
        bad = copy.deepcopy(worker);bad['final_resume_next_episode_indices'][0]+=1
        with self.assertRaisesRegex(ValueError,'terminal episodes/assignments differ'):
            terminal.validate_outputs(self.reg,bad,self.envelope['registration_sha256'])

    def completed_fixture(self):
        """A tiny deterministic JSON producer, never an environment or trainer."""
        c = b.contracts();out=Path(self.reg['output']);out.mkdir()
        next_indices=list(self.reg['initial_episode_indices']); assignments=[];active={}; frames=[0]*64;completions=[];resets=[]
        def assign(slot,update,decision):
            episode=next_indices[slot];next_indices[slot]+=1
            md=c.seed_metadata(self.reg['vector']['seeds']['env_master_seed'],slot,episode,self.reg['exclusion_union'])
            seed=dict(slot=slot,episode=episode,actual_seed=md['first_actual_seed'],counter=md['rejection_counter'],evaluation=False)
            row=dict(update=update,decision=decision,slot=slot,generation=None,horizon=18000,ordinal=None,seed=seed,block=None,position=None,vector_hash=None)
            active[slot]=row;assignments.append(row);return row
        def info(slot,ended=False):
            return dict(seed=active[slot]['seed'],startup_frames=13,gameplay_frames=frames[slot],alive_frames=frames[slot],terminated=False,truncated=ended)
        initial_assign=[assign(s,0,-1) for s in range(64)]
        events=[dict(kind='initial',info=[info(s) for s in range(64)],assignments=initial_assign)]
        metrics=[];boundaries=[]
        for local in range(1,61):
            for decision in range(256):
                events.append(dict(kind='returned_step_cost',update=local,decision=decision,elapsed_raw_frames=[4]*64))
                frames=[f+4 for f in frames]
                if frames[0]==18000:
                    for s in range(64):
                        row=dict(update=local,decision=decision,slot=s,generation=None,horizon=18000,ordinal=None,success=True,scheduler_generation=None,native_info=info(s,True))
                        completions.append(row);events.append(dict(kind='completion',**row))
                    frames=[0]*64
                    # Native reset reports the next episode before adapter assignment.
                    new_rows=[assign(s,local,decision) for s in range(64)]
                    reset=dict(update=local,decision=decision,indices=list(range(64)),info=[info(s) for s in range(64)])
                    resets.append(reset);events.append(dict(kind='returned_reset',**reset))
                    events.extend(dict(kind='reset_assignment',**r) for r in new_rows)
            events.append(dict(kind='collection_complete_before_PPO',global_update=local))
            boundary=dict(completed_update=local,promoted=False,generation_after_boundary=None);boundaries.append(boundary)
            counters=dict(updates=local,optimizer_steps=local,environment_decisions=local*16384,raw_frames=local*65536)
            metrics.append(dict(global_update=local,phase_update=324+local,cumulative_update=372+local,effective_learning_rate=3e-5,
                metrics=dict(optimizer_steps=1,transitions=16384),progress=dict(complete=True,in_update=False,optimizer_steps=1),counters=counters,scheduler_boundary=boundary))
        reset_count=sum(len(r['indices']) for r in resets);raw=60*65536;total=raw+832+reset_count*13
        env=dict(completed_updates=60,pending_update=None,returned_work_not_accepted_by_audit=0,
            returned_native_gameplay_frames_unaudited=raw,gameplay_frames_including_fatal=raw,returned_native_vector_steps=60*256,
            initial_construction_startup_frames=832,normal_reset_count=reset_count,returned_reset_startup_frames_unaudited=reset_count*13,
            reset_startup_frames=reset_count*13,accepted_raw_frames_total=total,raw_frames_total_including_returned_unaudited_work=total,
            returned_resets=resets,assignments=assignments,completions=completions,boundaries=boundaries,scheduler=None,
            consumed_actual_seed_union=sorted(r['seed']['actual_seed'] for r in assignments),
            in_flight=[dict(slot=s,assignment_status='assigned',native_info=info(s)) for s in range(64)])
        snapshot=dict(state='ready',completed_optimizer_steps=60,actual_optimizer_steps_including_failed_update=60,environment=env)
        checkpoints=[]
        for local in (12,24,36,48,60):
            path=out/f'checkpoint-global-{local:03d}-integrity.pt';path.write_bytes(b'SYNTHETIC JSON CONTROL - NOT A CHECKPOINT')
            record=dict(path=str(path),sha256=b.sha(path),global_update=local,phase_update=324+local,cumulative_update=372+local,
                formal_comparison_endpoint=local==60,training_eligible=False,promoted=False,automatic_selection=False)
            b.save(str(path)+'.json',record);checkpoints.append(record)
        worker=dict(status='completed',updates=60,run_id=self.reg['run_id'],registration_sha256=self.envelope['registration_sha256'],
            training_eligible=False,promoted=False,automatic_selection=False,evaluated_updates=[],phase_update=384,cumulative_update=432,
            elapsed_seconds=1,counters=counters,final_snapshot=snapshot,curriculum_snapshot=snapshot,final_resume_next_episode_indices=next_indices,
            integrity_checkpoints=checkpoints,formal_comparison_endpoint=checkpoints[-1],peak_rss_bytes=1,peak_mps_driver_bytes=1)
        ref=c.references.load_bound_reference(receipt_path=self.reg['reference']['receipt_path'],expected_receipt_sha256=self.reg['reference']['receipt_sha256'],
            expected_study_id=self.reg['study_id'],expected_replica=self.reg['replica'],expected_seed_vector=self.reg['vector']['seeds'],
            expected_vector_sha256=self.reg['vector']['vector_sha256'],expected_torch_version=self.reg['runtime_versions']['torch'])
        entry=dict(study_id=self.reg['study_id'],pair_id=self.reg['pair_id'],replica=self.reg['replica'],arm=self.reg['arm'],backend=self.reg['backend'],
            seed_vector=self.reg['vector']['seeds'],vector_sha256=self.reg['vector']['vector_sha256'],parent_fingerprints=self.reg['expected_parent_fingerprints'],
            seed_evidence=dict(torch_cpu_rng_state_sha256=ref['torch_cpu_global_seed'],torch_mps_rng_state_sha256=ref['action_sampler_torch_mps_seed'],torch_cpu_initial_seed=self.reg['vector']['seeds']['torch_cpu_global_seed']),
            new_controller=dict(kind='constant',origin=372,horizon=60,first_update=373,last_update=432,start_lr=3e-5,end_lr=3e-5),
            post_lr_fingerprints=self.reg['expected_parent_fingerprints'],adapter_post_reseed_components=dict(torch_cpu=ref['torch_cpu_global_seed'],torch_mps=ref['action_sampler_torch_mps_seed']))
        b.save(out/'entry-restoration.json',entry)
        (out/'training-events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in events))
        (out/'training-metrics.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in metrics))
        (out/'resources.jsonl').write_text('{"rss_bytes":1,"mps_driver_bytes":1}\n')
        return worker


if __name__ == '__main__':
    unittest.main(verbosity=2)
