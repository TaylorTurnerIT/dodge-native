"""Bounded CPU fake-process tests for full CLI signal windows."""
import json, os, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from test_runner import fixture, sha

class SignalWindowTests(unittest.TestCase):
 def cli(self,f):
  return [sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])]
 def receipt(self,f):return f['out'].with_suffix('.json.outer-receipt.json')
 def repin(self,f):
  reg=json.loads(f['reg'].read_text());reg['source']['launcher_sha256']=sha(f['launcher']);reg['source']['evaluator_sha256']=sha(f['evaluator']);f['reg'].write_text(json.dumps(reg,sort_keys=True)+'\n');f['regsha']=sha(f['reg'])
 def test_signal_during_postflight_reaps_orphan_group_and_writes_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td)
   f['evaluator'].write_text(f['evaluator'].read_text().replace(" check_guard()\n print('EVAL_START'", " check_guard()\n child=os.fork()\n if child==0: os._exit(0)\n os.waitpid(child,0); os.write(1,b'CHILD_PID='+str(child).encode()+b'\\n')\n print('EVAL_START'"))
   sentinel=Path(td)/'postflight-entered'
   f['launcher'].write_text(f['launcher'].read_text().replace("  rec=receipt(reg,registration_sha256,stage,candidate_update,cohort,start,reason,exit_code,rows,log);atomic_json(receipt_path,rec)", f"  Path({str(sentinel)!r}).write_text('ready')\n  time.sleep(5)\n  rec=receipt(reg,registration_sha256,stage,candidate_update,cohort,start,reason,exit_code,rows,log);atomic_json(receipt_path,rec)"));self.repin(f)
   p=subprocess.Popen(self.cli(f),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   end=time.time()+12
   while time.time()<end and not sentinel.exists():time.sleep(.02)
   self.assertTrue(sentinel.exists())
   line=next(x for x in f['log'].read_text().splitlines() if x.startswith('CHILD_PID='));child=int(line.split('=',1)[1])
   if p.poll() is not None: self.fail('runner exited before signal: '+str(p.communicate(timeout=1)))
   os.kill(p.pid,signal.SIGTERM);p.communicate(timeout=12)
   self.assertTrue(self.receipt(f).exists());r=json.loads(self.receipt(f).read_text());self.assertIn('supervisor_signal',r['stop_reason']);self.assertTrue(r['process_group_absent'])
   with self.assertRaises(ProcessLookupError):os.kill(child,0)
 def test_sigterm_during_popen_return_is_deferred_until_proc_assignment(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=30,heartbeat_stale=5);src=f['launcher'].read_text()
   needle="    try:proc=subprocess.Popen(cmd,start_new_session=True,stdout=lf,stderr=subprocess.STDOUT,close_fds=True)"
   replacement="    try:\n     proc=subprocess.Popen(cmd,start_new_session=True,stdout=lf,stderr=subprocess.STDOUT,close_fds=True)\n     os.kill(os.getpid(),signal.SIGTERM)"
   self.assertIn(needle,src);f['launcher'].write_text(src.replace(needle,replacement));self.repin(f)
   p=subprocess.run(self.cli(f),capture_output=True,text=True,timeout=18)
   self.assertNotEqual(p.returncode,0);self.assertTrue(self.receipt(f).exists());r=json.loads(self.receipt(f).read_text());self.assertIn('supervisor_signal',r['stop_reason']);self.assertTrue(r['process_group_absent'])
if __name__=='__main__':unittest.main()
