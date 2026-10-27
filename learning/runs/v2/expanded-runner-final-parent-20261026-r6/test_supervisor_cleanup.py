"""Signal and sampling regressions against the integrated runner fixture."""
import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from test_runner import fixture,invoke

class CleanupTests(unittest.TestCase):
 def signal_case(self,signame):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=30,heartbeat_stale=5)
   cmd=[sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])]
   p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   deadline=time.time()+10
   while (not f['log'].exists() or 'EVAL_START' not in f['log'].read_text()) and time.time()<deadline:time.sleep(.03)
   os.kill(p.pid,getattr(__import__('signal'),signame));p.communicate(timeout=12)
   rec=f['out'].with_suffix('.json.outer-receipt.json')
   self.assertTrue(rec.exists());d=json.loads(rec.read_text());self.assertIn('supervisor_signal',d['stop_reason']);self.assertTrue(d['process_group_absent']);self.assertTrue(f['marker'].exists())
 def test_sigterm_reaps_group_and_writes_partial_receipt(self):self.signal_case('SIGTERM')
 def test_sighup_reaps_group_and_writes_partial_receipt(self):self.signal_case('SIGHUP')
 def test_outer_receipt_collision_does_not_claim_marker(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);rec=f['out'].with_suffix('.json.outer-receipt.json');rec.parent.mkdir(parents=True,exist_ok=True);rec.write_text('preserve')
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists());self.assertEqual(rec.read_text(),'preserve')
 def test_ps_failure_during_stop_keeps_receipt_and_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=30,heartbeat_stale=5)
   wrapper=f['d']/'bin';wrapper.mkdir();ps=wrapper/'ps';ps.write_text('#!/bin/sh\nexit 1\n');ps.chmod(0o755)
   env=dict(os.environ);env['PATH']=str(wrapper)+os.pathsep+env['PATH']
   cmd=[sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])]
   p=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);time.sleep(.5);os.kill(p.pid,__import__('signal').SIGTERM);p.communicate(timeout=12)
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());d=json.loads(rec.read_text());self.assertFalse(d['process_group_absent']);self.assertIn('sampling_failed',d['stop_reason'])
 def test_ps_failure_after_exit_keeps_receipt_and_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td)
   wrapper=f['d']/'bin';wrapper.mkdir();ps=wrapper/'ps';counter=f['d']/'counter';ps.write_text('#!/bin/sh\nn=$(cat "'+str(counter)+'" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "'+str(counter)+'"; if [ $n -gt 1 ]; then exit 1; fi; exec /bin/ps "$@"\n');ps.chmod(0o755)
   env=dict(os.environ);env['PATH']=str(wrapper)+os.pathsep+env['PATH']
   cmd=[sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])]
   p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=12);rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());self.assertNotEqual(p.returncode,0);self.assertFalse(json.loads(rec.read_text())['process_group_absent'])
