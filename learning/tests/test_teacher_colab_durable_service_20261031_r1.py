"""Production warm-service entry with real SDK store and loopback-only HTTP.

The child runs the unchanged adapter main. Only cloud authentication and its
HTTPS destination are replaced: credentials are forbidden and requests route
to this local HTTP fixture. This does not test live Colab or TLS negotiation.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
EXPERIMENTS=ROOT/'learning/experiments'
PARENT=ROOT/'learning/runs/v2/teacher-cloud-parent-20261031-r1'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


t=module('durable_service_transport',EXPERIMENTS/'teacher_colab_durable_transport_20261031_r1.py')
repin=module('service_dependency_pins',EXPERIMENTS/'teacher_colab_training_repin_20261031_r1.py')

BOOTSTRAP='''
import runpy,sys
from urllib.parse import urlparse,urlunparse
import requests
from colab_cli import common
def forbidden(*a,**k):raise AssertionError('Cloud credentials/account access forbidden in CPU fixture')
common.get_credentials=forbidden
common.State.client=property(forbidden)
port=sys.argv[1];adapter=sys.argv[2];original=requests.Session.request
def local_only(self,method,url,*a,**k):
    parsed=urlparse(url)
    if method!='PUT' or parsed.scheme!='https' or parsed.netloc!='fixture.invalid':
        raise AssertionError('Non-loopback control request forbidden')
    redirected=urlunparse(('http','127.0.0.1:'+port,parsed.path,'','',''))
    return original(self,method,redirected,*a,**k)
requests.Session.request=local_only
sys.argv=[adapter,*sys.argv[3:]]
runpy.run_path(adapter,run_name='__main__')
'''


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*_):pass
    def do_PUT(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.received.append((self.client_address,body))
        data=b'{}';self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers()
        self.wfile.write(data)


class RealServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.daemon_threads=True
        cls.server.received=[];cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name);self.transport=None
        self.received_before=len(self.server.received)
    def tearDown(self):
        if self.transport:self.transport.close_control()
        self.directory.cleanup()
    def start(self,*,missing=False,bad_digest=False):
        candidate=PARENT/'DODGE-062-A100-training-registration-r2.json'
        if missing or not candidate.exists():candidate=PARENT/'DODGE-062-A100-training-registration-r1.json'
        reg=copy.deepcopy(json.loads(candidate.read_text()))
        if not missing and candidate.name.endswith('r1.json'):reg['input_pins'].update(repin.dependency_pins())
        reg['record']='DODGE-064'
        paths=[EXPERIMENTS/name for name in ['teacher_colab_durable_dispatch_20261031_r1.py','teacher_colab_durable_transport_20261031_r1.py','teacher_colab_durable_budget_20261031_r1.py','teacher_colab_durable_channel_20261031_r1.py']]
        reg['coordinator_source_pins']={str(path):t.c.sha(path) for path in paths}
        reg['source_pins'].update(reg['coordinator_source_pins'])
        reg['control_channel_path']=str(paths[-1])
        if bad_digest:
            path=next(p for p in reg['input_pins'] if p.endswith('/idna/core.py'));reg['input_pins'][path]='0'*64
        reg.update(job_nonce=str(uuid.uuid4()),expected_lease={'CPU_fixture_only':True},cli_config_path=str(self.root/'private.json'),
                   state_path=str(self.root/'fixture-state.json'),empty_pycache=str(self.root/'empty-cache'))
        Path(reg['empty_pycache']).mkdir()
        reg['expected_lease_sha256']=__import__('hashlib').sha256(t.c.canonical(reg['expected_lease'])).hexdigest()
        private={reg['session_name']:dict(name=reg['session_name'],endpoint='CPU-only-endpoint',accelerator='A100',
            variant='GPU',machine_shape='STANDARD',token='NEVER_PUBLISH_FIXTURE_SECRET',url='https://fixture.invalid')}
        Path(reg['cli_config_path']).write_text(json.dumps(private));Path(reg['state_path']).write_text(json.dumps({'active_long_campaign':reg['expected_lease']}))
        t.c.save(self.root/'owned-endpoint.json',dict(name=reg['session_name'],endpoint='CPU-only-endpoint',accelerator='A100',notebook_hash=reg['job_nonce']))
        registration=self.root/'CPU-fixture-registration.json';registration.write_text(json.dumps(reg,sort_keys=True))
        reg['registration_sha256']=t.c.sha(registration)
        # This fixture cannot pass production validate_plan: expected_lease and
        # state_path deliberately differ from the real immutable authority.
        review=self.root/'CPU-fixture-review.json';review.write_text(json.dumps(dict(CPU_fixture_only=True,
            status='no_blocking_findings',registration_sha256=reg['registration_sha256'],coordinator_source_pins=reg['coordinator_source_pins'])))
        plan=dict(CPU_fixture_only=True,registration_path=str(registration),registration_sha256=reg['registration_sha256'],
                  review_path=str(review),review_sha256=t.c.sha(review),authority_path=reg['authority_path'],authority_sha256=reg['authority_sha256'])
        path=self.root/'CPU-fixture-plan.json';path.write_text(json.dumps(plan,sort_keys=True))
        transport=t.Transport(path,t.c.sha(path),reg,self.root);transport.endpoint='CPU-only-endpoint'
        self.reg=reg;self.transport=transport
        original=subprocess.Popen
        def spawn(command,**kwargs):
            self.assertEqual(command[-2:],['--sdk','control-server'])
            return original([command[0],'-B','-c',BOOTSTRAP,str(self.server.server_port),*command[2:]],**kwargs)
        with patch('subprocess.Popen',side_effect=spawn):transport.prepare_control(timeout=5)
        return transport
    def body(self):
        value={k:self.reg[k] for k in ['record','job_nonce','registration_sha256','expected_lease_sha256']}
        value.update(issued_at_utc=time.time(),expires_at_utc=time.time()+45,sequence=1,allowed_stage='build')
        return value
    def test_rejected_r1_reproduces_failure_before_readiness_and_HTTP(self):
        with self.assertRaisesRegex(ValueError,'startup identity'):self.start(missing=True)
        self.assertEqual(len(self.server.received),self.received_before)
        self.assertTrue((self.root/'control-server.claimed').exists())
    def test_actual_entry_readiness_and_many_PUTs_keep_one_process_connection(self):
        transport=self.start();pid=transport.control.process.pid
        for sequence in range(1,6):
            body=self.body();body['sequence']=sequence
            transport.put_json('/content/dodge064/control.json',body,timeout=2)
        rows=self.server.received[self.received_before:]
        self.assertEqual(len(rows),5);self.assertEqual(len({address for address,_ in rows}),1)
        self.assertEqual(pid,transport.control.process.pid)
        self.assertNotIn('NEVER_PUBLISH_FIXTURE_SECRET',(self.root/'control-transport.jsonl').read_text())
    def test_actual_entry_rejects_wrong_dependency_hash_before_readiness(self):
        with self.assertRaisesRegex(ValueError,'startup identity'):self.start(bad_digest=True)
        self.assertEqual(len(self.server.received),self.received_before)
    def test_actual_service_lease_loss_prevents_HTTP(self):
        transport=self.start();Path(self.reg['state_path']).write_text('{"active_long_campaign":null}')
        with self.assertRaises(ValueError):transport.put_json('/content/dodge064/control.json',self.body(),2)
        self.assertEqual(len(self.server.received),self.received_before)
    def test_actual_service_wrong_control_identity_prevents_HTTP(self):
        transport=self.start();body=self.body();body['job_nonce']='foreign'
        with self.assertRaises(ValueError):transport.put_json('/content/dodge064/control.json',body,2)
        self.assertEqual(len(self.server.received),self.received_before)
    def test_actual_service_cancellation_prevents_later_grants(self):
        transport=self.start();transport.put_json('/content/dodge064/cancel.requested',{'requested':True},2)
        with self.assertRaises(ValueError):transport.put_json('/content/dodge064/control.json',self.body(),2)
        self.assertEqual(len(self.server.received)-self.received_before,1)
    def test_actual_service_preserves_exact_admission_bytes(self):
        transport=self.start();body={k:self.reg[k] for k in ['record','job_nonce','registration_sha256','expected_lease_sha256']}
        body['accepted_build_certificate_sha256']='d'*64;data=(json.dumps(body,indent=2)+'\n').encode()
        transport.put_json('/content/dodge064/runtime-admission.json',body,2,exact_bytes=data)
        self.assertEqual(self.server.received[-1][1]['content'].encode(),data)


if __name__=='__main__':unittest.main(verbosity=2)
