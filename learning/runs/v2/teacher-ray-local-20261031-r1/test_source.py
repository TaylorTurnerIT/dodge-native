"""CPU/stdlib lifecycle and evaluator fixtures; no native games or lease writes."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import common as c
import lifecycle
import run_once
from worker import PreparedUpdates, failure_observations
from evaluate_worker import Executor,domain_seed,summary


class SourceTests(unittest.TestCase):
    def test_failed055_handoff_requires_failed_status_exact_owner_and_durable_hashes(self):
        import copy
        with tempfile.TemporaryDirectory() as d:
            old=dict(kind='teacher_ray_training_screen',owner_token='rays055-r3')
            new=dict(kind='teacher_ray_training_screen',owner_token='rays056-r4')
            reg=dict(record='DODGE-066',expected_lease=new,
                failed_predecessor=dict(expected_lease=old,registration_sha256='old055reg'))
            failure=dict(status='acknowledged_failed_campaign',record='DODGE-065',campaign_success=False,
                registration_sha256='old055reg',exact_lease=old,review_sha256='review',authority_sha256='authority')
            handoff=dict(status='exact_non_null_failed_campaign_handoff',previous_lease=old,replacement_lease=new,
                registration_sha256='new056reg',authority_sha256='authority',never_cleared_to_null=True)
            for case in ('valid','null','direct051','success','wrong_registration','wrong_review','not_durable'):
                f=copy.deepcopy(failure);h=copy.deepcopy(handoff)
                if case=='null':h['previous_lease']=None
                if case=='direct051':h['previous_lease']=dict(kind='K1_horizon_training_screen',owner_token='051')
                if case=='success':f['campaign_success']=True
                if case=='wrong_registration':h['registration_sha256']='other'
                if case=='wrong_review':f['review_sha256']='other'
                fp=Path(d)/(case+'-failure.json');hp=Path(d)/(case+'-handoff.json')
                c.save(fp,f);h['failure_disposition_sha256']=c.sha(fp);c.save(hp,h)
                gate=dict(failure_disposition_path=str(fp),failure_disposition_sha256=c.sha(fp),
                    lease_handoff_path=str(hp),lease_handoff_sha256=c.sha(hp),registration_sha256='new056reg',
                    review_sha256='review',authority_sha256='authority')
                if case=='not_durable':gate['lease_handoff_sha256']='wrong'
                if case=='valid':run_once.validate_failed_handoff(reg,gate)
                else:
                    with self.assertRaises(ValueError):run_once.validate_failed_handoff(reg,gate)

    def test_stale_runtime_cache_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'module.py').write_text('pass\n')
            reg=dict(runtime_root=str(root),runtime_members=['module.py'])
            c.verify_runtime_members(reg)
            (root/'__pycache__').mkdir()
            (root/'__pycache__/module.cpython-312.pyc').write_bytes(b'stale')
            with self.assertRaisesRegex(ValueError,'Runtime member set drift'):
                c.verify_runtime_members(reg)
    def power_run_fixture(self, sources):
        actual_run=subprocess.run
        readings=iter(sources);last=['Battery Power']
        def run(argv,*args,**kwargs):
            if argv[:3]==['/usr/bin/pmset','-g','batt']:
                try:last[0]=next(readings)
                except StopIteration:pass
                if isinstance(last[0],Exception):raise last[0]
                return SimpleNamespace(stdout=f"Now drawing from '{last[0]}'\n -InternalBattery 45%; discharging;\n")
            if argv[:3]==['/usr/bin/pmset','-g','assertions']:
                return SimpleNamespace(stdout='pid 54321(caffeinate): PreventUserIdleSystemSleep named: fixture\n')
            if argv==['/bin/ps','-axo','pid=,ppid=,pgid=,command=']:
                return SimpleNamespace(stdout='54321 12345 54321 /usr/bin/caffeinate -ims -w 12345\n')
            return actual_run(argv,*args,**kwargs)
        return run

    def run_power_dummy(self,sources):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);journal=c.Journal(out/'power.jsonl')
            with patch.object(c.subprocess,'run',side_effect=self.power_run_fixture(sources)):
                def monitor(_):
                    c.record_power(journal,sleep=c.power_assertions(12345))
                result=lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(.7)'],
                    out,dict(os.environ),monitor,10)
            journal.close()
            rows=[json.loads(x) for x in (out/'power.jsonl').read_text().splitlines()]
            self.assertEqual(result['raw_exit_code'],0)
            self.assertTrue(result['group_absent'])
            return rows

    def test_initial_battery_and_missing_AC_specific_assertion_complete_child(self):
        rows=self.run_power_dummy(['Battery Power'])
        self.assertTrue(all(r['power']['source']=='Battery Power' for r in rows))
        self.assertTrue(all(r['sleep']['assertions']==['PreventUserIdleSystemSleep'] for r in rows))

    def test_AC_to_battery_transition_completes_running_dummy(self):
        rows=self.run_power_dummy(['AC Power','Battery Power'])
        self.assertEqual(rows[0]['power']['source'],'AC Power')
        self.assertIn('Battery Power',[r['power']['source'] for r in rows[1:]])

    def test_failed_power_probe_is_logged_unavailable_and_child_completes(self):
        rows=self.run_power_dummy([subprocess.TimeoutExpired('pmset',3)])
        self.assertTrue(all(r['power']['status']=='unavailable' for r in rows))
        with patch.object(c.subprocess,'run',return_value=SimpleNamespace(stdout='malformed')):
            self.assertEqual(c.passive_power()['status'],'unavailable')
        with patch.object(c.subprocess,'run',side_effect=c.CampaignStop('deadline')):
            with self.assertRaises(c.CampaignStop):c.passive_power()

    def test_resource_and_lease_stops_still_terminate_dummy_on_battery(self):
        for reason in ('RSS','lease','wall'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
                out=Path(d)
                reg=dict(state_path='mock-only',expected_lease={'token':'fixture'},rss_bytes=100,
                         mps_bytes=100)
                state={'active_long_campaign':{'token':'lost' if reason=='lease' else 'fixture'}}
                with patch.object(c.subprocess,'run',side_effect=self.power_run_fixture(['Battery Power'])),\
                     patch.object(c,'read',return_value=state),patch.object(c,'process_rss',return_value=1):
                    def monitor(_):
                        self.assertEqual(c.passive_power()['source'],'Battery Power')
                        c.check_observer_resources(reg,[dict(rss_bytes=100 if reason=='RSS' else 0)],1,54321)
                    with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                        lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(60)'],out,
                            dict(os.environ),monitor,.15 if reason=='wall' else 10,2)
                self.assertTrue(c.read(out/'exit.json')['group_absent'])
        with patch.object(c,'check_lease'):
            for rss,mps in ((100,0),(0,100)):
                with self.assertRaisesRegex(ValueError,'resource ceiling'):
                    c.check_worker_resources(reg,rss,mps)

    def prepared_fixture(self):
        class Adapter:
            env=object()
            completed_updates=0
            pending_update=None
            gameplay_frames=0
            observed_native_steps=0
            def begin_update(self,update):
                if update!=self.completed_updates+1 or self.pending_update is not None:
                    raise ValueError('Fake update order')
                self.pending_update=update
            def returned(self):
                self.observed_native_steps+=1
                self.gameplay_frames+=64
            def _finish_after_ppo(self):
                self.completed_updates+=1;self.pending_update=None
                return dict(completed_updates=self.completed_updates)
        adapter=Adapter()
        ppo=SimpleNamespace(optimizer_calls=0,vectors=1024,fail_optimizer=False)
        def collect(*args,check_guard=None,**kwargs):
            for _ in range(ppo.vectors):
                adapter.returned()
                if check_guard is not None:check_guard()
            actions=SimpleNamespace(shape=(ppo.vectors,64),numel=lambda:ppo.vectors*64)
            return SimpleNamespace(batch=SimpleNamespace(actions=actions))
        def optimize(*args,progress,**kwargs):
            ppo.optimizer_calls+=1
            if ppo.fail_optimizer:
                progress.update(optimizer_steps=1,phase='optimization')
                raise RuntimeError('Synthetic optimizer interruption')
            progress.update(complete=True,in_update=False,phase='complete')
            return dict(optimizer_steps=1)
        ppo.collect_rollout=collect;ppo.ppo_update=optimize
        config=SimpleNamespace(learning_rate=3e-5,adam_eps=1e-5)
        optimizer=SimpleNamespace(param_groups=[dict(lr=3e-5,eps=1e-5)])
        reg=dict(rollout=1024,microbatch=512,effective_minibatch=2048,frame_target=2359296)
        return PreparedUpdates(None,optimizer,adapter,config,ppo,reg,'cpu'),ppo

    def test_interrupted_next_collection_cannot_reuse_last_successful_batch(self):
        prepared,ppo=self.prepared_fixture()
        first=prepared.update_once()
        self.assertIs(first,prepared.last_result)
        self.assertEqual(prepared.collected_valid_vectors,1024)
        first_snapshot=failure_observations(prepared)
        def interrupt():
            if prepared.adapter.observed_native_steps==1026:
                raise KeyboardInterrupt('Synthetic interruption after two returned vectors')
        with self.assertRaises(KeyboardInterrupt):prepared.update_once(check_guard=interrupt)
        observed=failure_observations(prepared)
        self.assertEqual(observed['attempted_update'],2)
        self.assertEqual(observed['collection_status'],'interrupted_before_return')
        self.assertIsNone(observed['collected_valid_vectors'])
        self.assertIsNone(observed['collected_valid_transitions'])
        self.assertEqual(observed['observed_returned_vectors_this_attempt'],2)
        self.assertEqual(observed['observed_returned_frames_this_attempt'],128)
        self.assertEqual(observed['observed_gameplay_frames'],65664)
        self.assertEqual(prepared.progress['phase'],'collection')
        self.assertFalse(prepared.progress['complete'])
        self.assertEqual(ppo.optimizer_calls,1)
        self.assertEqual(prepared.adapter.completed_updates,1)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'first-failure.json'
            c.save(path,observed)
            self.assertEqual(c.read(path),observed)
        self.assertEqual(first_snapshot['collected_valid_vectors'],1024)

    def test_optimizer_interruption_reports_current_returned_partial_batch(self):
        prepared,ppo=self.prepared_fixture();prepared.update_once()
        ppo.vectors=2;ppo.fail_optimizer=True
        with self.assertRaisesRegex(RuntimeError,'Synthetic optimizer interruption'):
            prepared.update_once()
        observed=failure_observations(prepared)
        self.assertEqual(observed['attempted_update'],2)
        self.assertEqual(observed['collection_status'],'returned_valid_batch')
        self.assertEqual(observed['collected_valid_vectors'],2)
        self.assertEqual(observed['collected_valid_transitions'],128)
        self.assertEqual(observed['observed_returned_frames_this_attempt'],128)
        self.assertEqual(prepared.adapter.completed_updates,1)
        self.assertEqual(prepared.progress['optimizer_steps'],1)

    def test_real_command_builder_to_dummy_child_and_direct_reap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'r1-control';out.mkdir()
            (root/'worker.py').write_text('import argparse\np=argparse.ArgumentParser()\np.add_argument("--registration")\np.add_argument("--sha256")\np.add_argument("--job")\na=p.parse_args()\nassert a.job=="r1-control"\nprint(a.sha256)\n')
            with patch.object(c,'HERE',root):
                argv=run_once.argv_for(dict(interpreter=sys.executable),root/'no-real-registration','dummy-hash',dict(id='r1-control'))
                result=lifecycle.run_child(argv,out,dict(os.environ),lambda _:None,10)
            self.assertTrue(result['directly_reaped'] and result['group_absent'])
            self.assertEqual(result['raw_exit_code'],0)
            self.assertIn('dummy-hash',(out/'worker.log').read_text())

    def test_failed_dummy_preserves_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','raise SystemExit(7)'],out,dict(os.environ),lambda _:None,10)
            result=c.read(out/'exit.json');self.assertEqual(result['raw_exit_code'],7)
            self.assertTrue(result['directly_reaped'] and result['group_absent'])

    def test_dummy_timeout_terminates_before_reap(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(60)'],out,dict(os.environ),lambda _:None,.15,2)
            result=c.read(out/'exit.json')
            self.assertTrue(result['directly_reaped'] and result['group_absent'])
            self.assertIn(int(signal.SIGTERM),result['cleanup_signals'])

    def test_clean_identity_delay_start_neutral_fifo_and_reset(self):
        actions=[2,8,1,7,4,3,6]
        for delay in (0,1,4):
            condition='clean' if delay==0 else 'delay'+str(delay)
            executor=Executor(100,condition)
            got=[executor.apply(x) for x in actions]
            self.assertEqual(got,([0]*delay+actions)[:len(actions)])
            self.assertEqual(Executor(100,condition).apply(2),0 if delay else 2)

    def test_epsilon_includes_original_and_realized_changes(self):
        class Fixed:
            def random(self):return 0.0
            def randrange(self,n):self.n=n;return 3
        executor=Executor(100,'epsilon0.05');executor.rng=Fixed()
        self.assertEqual(executor.apply(3),3)
        self.assertEqual(executor.realized_changes,0)
        self.assertEqual(executor.apply(2),3)
        self.assertEqual(executor.realized_changes,1)
        self.assertEqual(executor.rng.n,9)
        self.assertNotEqual(domain_seed('policy',100,'clean'),domain_seed('executor',100,'clean'))
        self.assertNotEqual(domain_seed('executor',100,'clean'),domain_seed('executor',100,'delay1'))

    def test_marginal_quartiles_sort_each_condition(self):
        self.assertEqual(summary([9,3,1,7]),dict(Worst=1,Q1=1,Mean=5,Q4=9,Best=9))

    def test_publication_is_exclusive_and_no_lease_writer_exists(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'first.json';c.save(p,dict(first=True))
            with self.assertRaises(FileExistsError):c.save(p,dict(second=True))
            self.assertEqual(c.read(p),dict(first=True))
        self.assertFalse(hasattr(c,'lease_change'))
        self.assertNotIn('lease_change(',Path(run_once.__file__).read_text())

    def test_fixed_25_groups_paired_marginal_bootstrap_synthetic_rows(self):
        from evaluation_analysis import analyze
        models=['420','r1-control','r1-rays','r2-rays','r2-control']
        conditions=['clean','epsilon0.01','epsilon0.05','delay1','delay4']
        settings=dict(models=models,conditions=conditions,range_inclusive=[100,1123],
            groups=[dict(model=m,condition=k,count=1024 if k=='clean' else 256) for m in models for k in conditions],
            bootstrap_seed=109,bootstrap_draws=2000,milestones=[1000],early_death_max_frames=600)
        rows=[]
        for m in models:
            for k in conditions:
                for i in range(1024 if k=='clean' else 256):
                    rows.append(dict(model=m,condition=k,seed=100+i,alive_frames=100+i+(3 if m.endswith('rays') else 0)-(7 if k!='clean' else 0),terminated=True))
        result=analyze(rows,settings)
        self.assertEqual(len(result['groups']),25)
        for row in result['contrasts']:
            expected=3 if 'rays-minus-control' in row['comparison'] else -7
            self.assertEqual(row['difference']['Q1'],expected)
            self.assertEqual(row['percentile95']['Q1'],[expected,expected])


if __name__=='__main__':unittest.main(verbosity=2)
