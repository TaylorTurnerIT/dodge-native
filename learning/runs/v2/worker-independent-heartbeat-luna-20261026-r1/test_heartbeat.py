import importlib.util, json, pathlib, tempfile, threading, time, unittest

WORKER = pathlib.Path(__file__).with_name('worker.py')
spec = importlib.util.spec_from_file_location('heartbeat_worker', WORKER)
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

class SamplerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.hb=pathlib.Path(self.tmp.name)/'heartbeat.json'; self.calls=[]
  def guard(reg,rp,pin,deadline,hb,seq):
   seq+=1; self.calls.append(seq)
   w.update_json(hb,{'run_id':'run-test','registration_sha256':'a'*64,'pid':123,'sequence':seq,'rss_bytes':1,'mps_driver_bytes':0})
   return seq
  self.old=w.worker_guard; w.worker_guard=guard; self.addCleanup(setattr,w,'worker_guard',self.old)
  self.reg={'run_id':'run-test','runtime':{'backend':'cpu'},'limits':{'guard_poll_seconds':.02}}
 def test_live_during_blocking_work_and_identity_sequence(self):
  sampler=w.HeartbeatSampler(self.reg,'reg','a'*64,time.monotonic()+3,self.hb); sampler.start()
  time.sleep(.15)
  row=json.loads(self.hb.read_text()); self.assertGreaterEqual(len(self.calls),3)
  self.assertEqual((row['run_id'],row['registration_sha256'],row['pid']),('run-test','a'*64,123))
  self.assertEqual(row['sequence'],self.calls[-1])
  sampler.stop(); self.assertFalse(sampler.thread.is_alive())
 def test_guard_error_propagates(self):
  def fail(*args): raise RuntimeError('injected sampler failure')
  w.worker_guard=fail
  sampler=w.HeartbeatSampler(self.reg,'reg','a'*64,time.monotonic()+2,self.hb); sampler.start()
  time.sleep(.05)
  with self.assertRaisesRegex(RuntimeError,'injected sampler failure'): sampler.check()
  with self.assertRaisesRegex(RuntimeError,'injected sampler failure'): sampler.stop()
  self.assertFalse(sampler.thread.is_alive())
 def test_mps_unavailable_after_module_ready_fails_closed(self):
  class MPS: 
   @staticmethod
   def is_available(): return False
  class Torch: backends=type('B',(),{'mps':MPS})()
  old=w.sys.modules.get('torch'); w.sys.modules['torch']=Torch
  self.addCleanup(lambda: w.sys.modules.pop('torch',None) if old is None else w.sys.modules.__setitem__('torch',old))
  self.reg['runtime']['backend']='mps'
  sampler=w.HeartbeatSampler(self.reg,'reg','a'*64,time.monotonic()+2,self.hb); sampler.start(); time.sleep(.05)
  with self.assertRaisesRegex(RuntimeError,'MPS driver memory unavailable'): sampler.check()
  try: sampler.stop()
  except RuntimeError: pass
  self.assertFalse(sampler.thread.is_alive())
 def test_startup_deadline_fails_closed(self):
  self.reg['runtime']['backend']='mps'
  old=w.sys.modules.pop('torch',None)
  sampler=w.HeartbeatSampler(self.reg,'reg','a'*64,time.monotonic()+3,self.hb); sampler.started-=13; sampler.start(); time.sleep(.05)
  with self.assertRaisesRegex(RuntimeError,'startup readiness deadline'): sampler.check()
  try: sampler.stop()
  except RuntimeError: pass
  self.assertFalse(sampler.thread.is_alive())
  if old is not None: w.sys.modules['torch']=old
 def test_sequence_publication_is_atomic_and_cpu_does_not_import_torch(self):
  self.assertEqual(w.driver_memory_status('cpu'),(0,'runtime',False))
  self.assertNotIn('torch',w.sys.modules)
  self.test_live_during_blocking_work_and_identity_sequence()

if __name__=='__main__': unittest.main()
