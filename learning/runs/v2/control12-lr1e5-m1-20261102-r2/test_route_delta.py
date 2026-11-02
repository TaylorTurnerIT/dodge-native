"""Only new route/admission guard checks; no process, model or device work."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from ssh_route_guard import inspect_context,verify_preflight

B=dict(required_client_ip='100.93.220.126',required_server_ip='100.79.157.37',required_server_port=22,
       required_uid=501,required_euid=501)
I=dict(pid=123,ppid=122,pgid=122,uid=501,euid=501)
E=dict(SSH_CONNECTION='100.93.220.126 59701 100.79.157.37 22')


class RouteTests(unittest.TestCase):
    def run_fixture(self,**changes):
        return inspect_context(changes.get('binding',B),environ=changes.get('environ',E),
            identity=changes.get('identity',I),run=changes.get('run',lambda *a,**kw:SimpleNamespace(stdout='123 122 122 20480\n',returncode=0)))
    def test_actual_route_and_process_fixture_pass(self):
        result=self.run_fixture();self.assertEqual(result['self_RSS_bytes'],20971520)
        self.assertEqual(result['ps_exit_code'],0)
    def test_missing_SSH_rejected_before_process_call(self):
        def forbidden(*a,**kw):raise AssertionError('Must reject before process call')
        with self.assertRaises(ValueError):self.run_fixture(environ={},run=forbidden)
    def test_wrong_source_or_target_rejected(self):
        for value in ['100.102.157.110 59701 100.79.157.37 22','100.93.220.126 59701 100.102.157.110 22']:
            with self.assertRaises(ValueError):self.run_fixture(environ={'SSH_CONNECTION':value})
    def test_wrong_user_rejected(self):
        with self.assertRaises(ValueError):self.run_fixture(identity=dict(I,euid=0))
    def test_denied_process_inspection_propagates(self):
        def denied(*a,**kw):raise PermissionError('Fixture process inspection denied')
        with self.assertRaises(PermissionError):self.run_fixture(run=denied)
    def test_process_identity_mismatch_rejected(self):
        with self.assertRaises(ValueError):self.run_fixture(run=lambda *a,**kw:SimpleNamespace(stdout='123 999 122 20480\n',returncode=0))
    def test_preflight_receipt_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'receipt.json';p.write_text('{}')
            with self.assertRaises(ValueError):verify_preflight(dict(B,preflight_receipt=str(p),preflight_receipt_sha256='0'*64))
    def test_accepted_lifecycle_receipt_required(self):
        receipt=dict(status='passed_actual_SSH_host_context_nontraining_preflight',context={'global_ps_exit':0},
            child_exit=dict(directly_reaped=True,group_absent=True,raw_exit_code=0,observed_exit_code=0),ledger_written=False,lease_operations=0)
        with tempfile.TemporaryDirectory() as tmp,patch('ssh_route_guard.inspect_context',return_value={'route':'fixture'}):
            p=Path(tmp)/'receipt.json';p.write_text(json.dumps(receipt))
            binding=dict(B,preflight_receipt=str(p),preflight_receipt_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(verify_preflight(binding)['route'],'fixture')
            receipt['child_exit']['directly_reaped']=False;p.write_text(json.dumps(receipt))
            binding['preflight_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):verify_preflight(binding)


if __name__=='__main__':unittest.main()
