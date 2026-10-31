"""Real persistent pipes and loopback HTTP; no cloud, secrets or engine access."""
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
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

SOURCE=Path(__file__).resolve().parents[1]/'experiments/teacher_colab_durable_channel_20261031_r1.py'
spec=importlib.util.spec_from_file_location('control_channel_tests',SOURCE)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

CHILD='''
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
c=module('fixture_channel',sys.argv[1])
t=module('fixture_transport',Path(sys.argv[1]).with_name('teacher_colab_training_transport_20261031_r2.py'))
import requests
from requests.adapters import HTTPAdapter
http=requests.Session();http.mount('http://',HTTPAdapter(max_retries=0))
session=SimpleNamespace(url=sys.argv[2],token='CPU-ONLY-DUMMY-TOKEN')
def handler(request):
    c.event(sys.argv[3],'worker','http_begin',request_id=request['id'])
    t.put_text(t.KeepaliveContents(session,http),request['remote'],request['content'].encode())
    c.event(sys.argv[3],'worker','http_complete',request_id=request['id'])
c.serve(handler,{'status':'fixture_ready'},sys.argv[3],input_stream=sys.stdin.buffer,output_stream=sys.stdout.buffer)
http.close()
'''


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*_):pass
    def do_PUT(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.received.append((self.client_address,body))
        mode=json.loads(body['content']).get('mode','ok')
        if mode=='slow':time.sleep(.3)
        status=500 if mode=='error' else 302 if mode=='redirect' else 200
        payload=b'{}';self.send_response(status);self.send_header('Content-Length',str(len(payload)));self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError):pass


class ChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.daemon_threads=True
        cls.server.received=[]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name);self.client=None
        self.journal=self.root/'timing.jsonl';self.before=len(self.server.received)
    def tearDown(self):
        if self.client:self.client.close()
        self.directory.cleanup()
    def start(self,program=CHILD,ready=None):
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',
                 PYTHONPATH='/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')
        command=[sys.executable,'-B','-c',program,str(SOURCE),
                 'http://127.0.0.1:'+str(self.server.server_port),str(self.journal)]
        self.client=c.PipeClient(command,env,self.journal,ready or {'status':'fixture_ready'},startup_timeout=5)
        return self.client
    def request(self,mode='ok',timeout=1):
        self.client.request('/content/dodge062/control.json',json.dumps({'mode':mode}).encode(),timeout=timeout)
    def test_many_real_PUTs_reuse_one_process_and_HTTP_connection(self):
        self.start();pid=self.client.process.pid
        for _ in range(20):self.request()
        rows=self.server.received[self.before:]
        self.assertEqual(len(rows),20);self.assertEqual(len({address for address,_ in rows}),1)
        self.assertEqual(self.client.process.pid,pid)
        self.assertTrue(all('chunk' not in body and body['format']=='text' for _,body in rows))
    def test_timeout_poison_reaps_and_never_retries_or_restarts(self):
        self.start()
        with self.assertRaises(TimeoutError):self.request('slow',timeout=.05)
        self.assertIsNotNone(self.client.process.poll())
        with self.assertRaisesRegex(ValueError,'permanently'):self.request()
        self.assertEqual(len(self.server.received[self.before:]),1)
        timing=[json.loads(line) for line in self.journal.read_text().splitlines()]
        self.assertTrue(any(x['phase']=='http_begin' for x in timing))
        self.assertFalse(any(x['phase']=='http_complete' for x in timing))
    def test_HTTP_error_is_single_attempt_and_redacted(self):
        self.start()
        with self.assertRaisesRegex(ValueError,'identity/status'):self.request('error')
        self.assertEqual(len(self.server.received[self.before:]),1)
        self.assertNotIn('CPU-ONLY-DUMMY-TOKEN',self.journal.read_text())
        self.assertNotIn('127.0.0.1',self.journal.read_text())
    def test_redirect_is_rejected_without_second_request(self):
        self.start()
        with self.assertRaises(ValueError):self.request('redirect')
        self.assertEqual(len(self.server.received[self.before:]),1)
    def test_startup_identity_mismatch_reaps(self):
        with self.assertRaisesRegex(ValueError,'startup identity'):self.start(ready={'status':'wrong'})
    def test_actual_child_exit_is_permanent(self):
        self.start();self.client.process.kill();self.client.process.wait()
        with self.assertRaises((EOFError,BrokenPipeError)):self.request()
        with self.assertRaisesRegex(ValueError,'permanently'):self.request()
    def test_exact_admission_bytes_are_preserved(self):
        self.start();body=b'{\n  "accepted": true\n}\n'
        self.client.request('/content/dodge062/runtime-admission.json',body,timeout=1)
        self.assertEqual(self.server.received[-1][1]['content'].encode(),body)
    def test_close_is_idempotent_and_ends_owned_process(self):
        self.start();process=self.client.process;self.client.close();self.client.close()
        self.assertIsNotNone(process.poll())
    def test_response_sequence_mismatch_poisoned(self):
        program="import sys,json;print(json.dumps({'status':'fixture_ready'}),flush=True);sys.stdin.readline();print(json.dumps({'id':99,'status':'complete'}),flush=True)"
        self.start(program)
        with self.assertRaisesRegex(ValueError,'identity/status'):self.request()
    def test_framing_cap_prevents_unbounded_child_output(self):
        program="import sys,json;print(json.dumps({'status':'fixture_ready'}),flush=True);sys.stdin.readline();print('x'*70000,flush=True)"
        self.start(program)
        with self.assertRaisesRegex(ValueError,'too large'):self.request()
    def test_oversized_request_poisoned_without_HTTP(self):
        self.start()
        with self.assertRaisesRegex(ValueError,'too large'):
            self.client.request('/content/dodge062/control.json',b'x'*70000,timeout=1)
        self.assertTrue(self.client.poisoned);self.assertIsNotNone(self.client.process.poll())
        self.assertEqual(len(self.server.received[self.before:]),0)
    def test_replayed_worker_request_never_calls_HTTP(self):
        self.start()
        os.write(self.client.process.stdin.fileno(),c.encoded(dict(id=2,remote='/content/dodge062/control.json',content='{}')))
        result=self.client.read_line(self.client.clock.now()+1)
        self.assertEqual(result,{'id':2,'status':'failure'})
        self.assertEqual(len(self.server.received[self.before:]),0)


if __name__=='__main__':unittest.main(verbosity=2)
