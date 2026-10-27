import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import probe

VECTORS=Path(__file__).parent.parent/"confirmed324-seed-vectors-parent-20261026-r1"/"seed-vectors.json"

class FakeMPS:
    def __init__(self, log): self.log=log
    def manual_seed(self, seed): self.log.append(("mps_seed",seed))
    def get_rng_state(self): self.log.append(("mps_state",)); return b"mps-state"

class FakeTorch:
    def __init__(self): self.log=[]; self.mps=FakeMPS(self.log)
    def manual_seed(self, seed): self.log.append(("cpu_seed",seed))
    def get_rng_state(self): self.log.append(("cpu_state",)); return b"cpu-state"

class ProbeTests(unittest.TestCase):
    def setUp(self): self.vectors=json.loads(VECTORS.read_text())
    def test_three_exact_refs_and_cpu_before_mps(self):
        api=FakeTorch(); fp=lambda b: __import__('hashlib').sha256(b).hexdigest()
        r=probe.capture_references(vectors=self.vectors,study_id=self.vectors['study_id'],torch_api=api,
            numpy_version='2.5.4',python_version='3.12.12',torch_version='2.14.1',backend_available=True,fingerprint=fp)
        self.assertEqual(len(r['references']),3)
        for ref in r['references']: self.assertEqual(set(ref),probe.RECEIPT_FIELDS)
        for n in range(0,len(api.log),4): self.assertEqual([x[0] for x in api.log[n:n+4]],['cpu_seed','mps_seed','cpu_state','mps_state'])
        self.assertEqual(api.log[1][1],self.vectors['vectors'][0]['seeds']['action_sampler_torch_mps_seed'])
    def test_rejects_missing_pending_or_wrong_parent_before_api(self):
        api=Mock()
        for mutate in (lambda v:v.update(vectors=v['vectors'][:2]),lambda v:v.update(status='measured')):
            v=json.loads(json.dumps(self.vectors)); mutate(v)
            with self.assertRaises(ValueError): probe.capture_references(vectors=v,study_id=v['study_id'],torch_api=api,numpy_version='2.5.4',python_version='3.12.12',torch_version='2.14.1',backend_available=True,fingerprint=str)
        with self.assertRaises(ValueError): probe.capture_references(vectors=self.vectors,study_id=self.vectors['study_id'],torch_api=api,numpy_version='2.5.4',python_version='3.12.12',torch_version='2.14.1',backend_available=True,fingerprint=str,checkpoint_sha256='0'*64)
        api.manual_seed.assert_not_called()
    def test_strict_int_and_full_vector_binding(self):
        v=json.loads(json.dumps(self.vectors)); v['vectors'][0]['seeds']['env_master_seed']=True
        with self.assertRaises(ValueError): probe.validate_vectors(v)
        v=json.loads(json.dumps(self.vectors)); v['vectors'][0]['seeds']['env_master_seed']+=1
        with self.assertRaises(ValueError): probe.validate_vectors(v)
    def test_zero_memory_allowed_excess_rejected_and_collision(self):
        with tempfile.TemporaryDirectory() as d:
            h=Path(d)/'heartbeat.json'; stop=__import__('threading').Event()
            identity={'run_id':'r','registration_sha256':'a'*64,'mps_cap_bytes':64}
            t=__import__('threading').Thread(target=probe.heartbeat_loop,args=(h,identity,stop,lambda:(0,0)))
            t.start(); __import__('time').sleep(.03); stop.set(); t.join(1)
            self.assertEqual(json.loads(h.read_text())['mps_driver_bytes'],0)
            with self.assertRaises(RuntimeError): probe.heartbeat_loop(h,identity,__import__('threading').Event(),lambda:(0,65))
            target=Path(d)/'out'
            refs=probe.capture_references(vectors=self.vectors,study_id=self.vectors['study_id'],torch_api=FakeTorch(),numpy_version='2.5.4',python_version='3.12.15',torch_version='2.14.1',backend_available=True,fingerprint=lambda b:__import__('hashlib').sha256(b).hexdigest())
            probe.atomic_publish(target,refs)
            self.assertTrue((target/'COMMITTED.json').is_file())
            with self.assertRaises(FileExistsError): probe.atomic_publish(target,refs)
            with self.assertRaises(ValueError): probe.atomic_publish(Path(d)/'partial',{'references':[1]})

if __name__=='__main__': unittest.main()
