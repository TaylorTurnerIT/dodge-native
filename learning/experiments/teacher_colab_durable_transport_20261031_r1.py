"""Bounded official Colab SDK/CLI adapter. Never persist proxy credentials.

The subprocess deadline also bounds ContentsClient, which has no HTTP timeout.
Live control uses a single non-chunked text PUT. Raw SDK models stay private.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid
from urllib.parse import quote, urlparse

SOURCE = Path(__file__).with_name('teacher_colab_durable_dispatch_20261031_r1.py')
spec = importlib.util.spec_from_file_location('dodge064_parent', SOURCE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def kill_local(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
    else:
        process.wait()


class SDKError(ValueError):
    def __init__(self,operation,failure_class,http_status=None):
        self.operation,self.failure_class,self.http_status=operation,failure_class,http_status
        super().__init__('Bounded SDK operation failed')


def bounded(command, env, timeout):
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException:
        kill_local(process)
        process.stdout.close()
        raise
    c.need(len(stdout)<=65536,'SDK output size cap')
    result=json.loads(stdout)
    if process.returncode!=0:
        status=result.get('http_status')
        status=status if type(status) is int and 100<=status<=599 else None
        operation=command[command.index('--sdk')+1] if '--sdk' in command else 'unknown'
        raise SDKError(operation,result.get('exception_type','UnknownSDKFailure'),status)
    return result


class Transport:
    def __init__(self, plan_path, plan_sha, reg, output):
        self.plan_path, self.plan_sha, self.reg = str(plan_path), plan_sha, reg
        self.output = Path(output); self.endpoint = None
        self.control = None; self.control_started = False
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
            PYTHONPYCACHEPREFIX=reg['empty_pycache'], COLAB_CLI_ASSIGN_RETRIES='0',
            COLAB_CLI_REQUEST_TIMEOUT='15')
        self.prefix = [reg['cli_path'], '--auth', 'oauth2', '--config', reg['cli_config_path']]

    def sdk(self, mode, timeout, **kwargs):
        args = [self.reg['sdk_python'], '-B', str(Path(__file__).resolve()),
                '--plan', self.plan_path, '--sha256', self.plan_sha, '--output', str(self.output), '--sdk', mode]
        for key, value in kwargs.items():
            args.extend(['--'+key.replace('_','-'), str(value)])
        return bounded(args, self.env, timeout)

    def snapshot(self, timeout):
        return self.sdk('snapshot', timeout)

    def allocate(self, nonce, timeout):
        result = self.sdk('allocate', timeout, nonce=nonce)
        self.endpoint = result['endpoint']
        return result

    def mkdir(self, remote, timeout):
        self.sdk('mkdir', timeout, remote=remote)

    def upload(self, local, remote, timeout):
        self.sdk('upload', timeout, local=local, remote=remote)

    def download(self, remote, local, timeout):
        self.sdk('download', timeout, local=local, remote=remote)

    def put_json(self, remote, value, timeout, *, exact_bytes=None):
        data = exact_bytes if exact_bytes is not None else c.canonical(value)
        if self.control is not None and not self.control.poisoned:
            return self.control.request(remote, data, timeout=timeout)
        # A failed control channel can never be restarted or grant work. Only
        # persistent cancellation may use a separate bounded cleanup request.
        c.need(remote == '/content/dodge064/cancel.requested', 'Live control channel unavailable; no rearm')
        temporary = self.output/('.cancel-transport-'+str(uuid.uuid4()))
        with temporary.open('xb') as stream:stream.write(data)
        try:
            self.sdk('put', timeout, local=temporary, remote=remote)
        finally:
            temporary.unlink()

    def prepare_control(self, timeout=15):
        c.need(not self.control_started, 'Control service already consumed; no restart')
        self.control_started = True
        c.save(self.output/'control-server.claimed', dict(record=self.reg['record'],job_nonce=self.reg['job_nonce']))
        channel = c.load(self.reg['control_channel_path'],self.reg['source_pins'][self.reg['control_channel_path']],
                         'dodge064_control_channel_parent')
        command = [self.reg['sdk_python'],'-B',str(Path(__file__).resolve()),'--plan',self.plan_path,
                   '--sha256',self.plan_sha,'--output',str(self.output),'--sdk','control-server']
        ready = dict(status='ready',registration_sha256=self.reg['registration_sha256'],
                     job_nonce=self.reg['job_nonce'],endpoint=self.endpoint)
        self.control = channel.PipeClient(command,self.env,self.output/'control-transport.jsonl',ready,
                                         startup_timeout=timeout)

    def close_control(self):
        if self.control is not None:self.control.close()

    def start(self, script, stage, timeout):
        checked_session(self.reg, self.output)
        c.need(script in [self.reg['unpack_script'], self.reg['stage_script']]
               and c.sha(script) == self.reg['source_pins'][script], 'Unpinned stage launcher')
        command = self.prefix+['exec', '-s', self.reg['session_name'], '-f', script, '--timeout', str(timeout),
            '--env', 'DODGE064_REGISTRATION_SHA256='+self.reg['registration_sha256'],
            '--env', 'DODGE064_STAGE='+stage, '--env', 'DODGE064_EXECUTION_ADMITTED=true']
        return subprocess.Popen(command, env=self.env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)

    def stop_local(self, process):
        kill_local(process)

    def unassign(self, endpoint, timeout):
        self.sdk('unassign', timeout, endpoint=endpoint)


def checked_session(reg, output):
    owned = c.read(Path(output)/'owned-endpoint.json')
    session = c.read(reg['cli_config_path']).get(reg['session_name'])
    c.need(owned['notebook_hash'] == reg['job_nonce'] and owned['name'] == reg['session_name']
           and isinstance(session, dict) and session.get('name') == owned['name']
           and session.get('endpoint') == owned['endpoint']
           and session.get('accelerator') == owned['accelerator'] == 'A100',
           'Private CLI session differs from durable ownership proof')
    return owned


def put_text(contents, remote, data):
    """Do not use chunk=1 for a liveness overwrite; exact admission bytes matter."""
    return contents._request('PUT', remote, json_data=dict(type='file', format='text',
        name=Path(remote).name, path=remote, content=data.decode('utf-8')))


def checked_origins(reg):
    for name,module in list(sys.modules.items()):
        if (name.startswith(('colab_cli.','requests.','urllib3.')) or name in ('colab_cli','requests','urllib3')) and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            pins=[v for p,v in reg['input_pins'].items() if Path(p).resolve()==path]
            c.need(pins and all(v==c.sha(path) for v in pins),'Loaded unpinned control dependency')


class KeepaliveContents:
    """Same official ContentsAPI text protocol, persistent HTTPS connection.

    One request, no redirects or retries. Socket bounds supplement the parent's
    unchanged eight-second total deadline; they do not extend it.
    """
    def __init__(self, session, http):
        self.session,self.http = session,http

    def _request(self, method, path, *, json_data):
        url = self.session.url.rstrip('/')+'/api/contents/'+quote(path.strip('/'),safe='/')
        response = self.http.request(method,url,
            params={'authuser':'0','colab-runtime-proxy-token':self.session.token},
            json=json_data,timeout=(2,5),allow_redirects=False)
        if 300 <= response.status_code < 400:raise ValueError('Contents redirect forbidden')
        response.raise_for_status()
        return response.json()


def serve_control(reg, output):
    """Warm SDK/file/HTTP objects once; re-check ownership on every PUT."""
    from colab_cli.common import State
    from colab_cli.auth import AuthProvider
    import requests
    from requests.adapters import HTTPAdapter
    channel = c.load(reg['control_channel_path'],reg['source_pins'][reg['control_channel_path']],
                     'dodge064_control_channel_worker')
    state=State();state.config_path=reg['cli_config_path'];state.auth_provider=AuthProvider.OAUTH2
    owned=checked_session(reg,output)
    checked_origins(reg)
    http=requests.Session()
    http.mount('https://',HTTPAdapter(max_retries=0))
    journal=Path(output)/'control-transport.jsonl';cancelled=False
    ready=dict(status='ready',registration_sha256=reg['registration_sha256'],job_nonce=reg['job_nonce'],endpoint=owned['endpoint'])
    def handler(request):
        nonlocal cancelled
        remote=request['remote'];identifier=request['id']
        c.need(remote in ['/content/dodge064/control.json','/content/dodge064/runtime-admission.json',
                          '/content/dodge064/cancel.requested'], 'Unregistered control path')
        c.need(not cancelled,'Cancellation permanently closes control service')
        if remote!='/content/dodge064/cancel.requested':c.lease_guard(reg)
        for path,digest in reg['coordinator_source_pins'].items():
            c.need(c.sha(path)==digest,'Control source changed')
        checked_session(reg,output)
        session=state.store.get(reg['session_name'])
        c.need(session is not None and session.endpoint==owned['endpoint']
               and session.accelerator=='A100' and urlparse(session.url).scheme=='https', 'Control ownership/proxy differs')
        body=request['content'].encode('utf-8');value=json.loads(body)
        if remote.endswith('control.json'):
            c.need(all(value.get(k)==reg[k] for k in ['record','job_nonce','registration_sha256','expected_lease_sha256']),
                   'Control identity differs')
        elif remote.endswith('runtime-admission.json'):
            c.need(all(value.get(k)==reg[k] for k in ['record','job_nonce','registration_sha256','expected_lease_sha256']),
                   'Admission identity differs')
        else:
            c.need(value.get('requested') is True,'Cancellation content differs');cancelled=True
        channel.event(journal,'worker','ownership_verified',request_id=identifier)
        channel.event(journal,'worker','http_begin',request_id=identifier)
        put_text(KeepaliveContents(session,http),remote,body)
        channel.event(journal,'worker','http_complete',request_id=identifier)
    try:
        channel.serve(handler,ready,journal,input_stream=sys.stdin.buffer,output_stream=sys.stdout.buffer)
    finally:http.close()


def sdk_adapter(reg, output, mode, *, nonce=None, endpoint=None, remote=None, local=None):
    os.umask(0o077)
    c.need(os.environ.get('COLAB_CLI_ASSIGN_RETRIES') == '0'
           and os.environ.get('COLAB_CLI_REQUEST_TIMEOUT') == '15', 'SDK retries/deadline environment differs')
    from colab_cli.common import State
    from colab_cli.auth import AuthProvider
    from colab_cli.client import Accelerator, Variant, Shape
    from colab_cli.consumption import CcuInfo
    from colab_cli.state import SessionState
    from colab_cli.contents import ContentsClient
    state = State(); state.config_path = reg['cli_config_path']; state.auth_provider = AuthProvider.OAUTH2

    def origins():
        for name, module in list(sys.modules.items()):
            if name.startswith('colab_cli.') and getattr(module, '__file__', None):
                path = Path(module.__file__).resolve()
                pins = [v for p, v in reg['input_pins'].items() if Path(p).resolve() == path]
                c.need(pins and all(v == c.sha(path) for v in pins), 'Loaded unpinned CLI source')
    origins()
    if mode == 'snapshot':
        raw = state.client._issue_request(state.client.colab_domain.rstrip('/')+'/tun/m/ccu-info',
                                          schema=CcuInfo).model_dump(by_alias=True)
        listed = state.client.list_assignments()
        assignments = [dict(endpoint=a.endpoint, accelerator=a.accelerator.value) for a in listed]
        session = state.store.get(reg['session_name'])
        # Reuse the already queried official assignment to renew proxy secrets
        # privately. Control PUTs never wait for OAuth or a second account call.
        if session is not None:
            from colab_cli.common import _apply_proxy_info
            match = next((a for a in listed if a.endpoint == session.endpoint),None)
            if match is not None:
                c.need(match.accelerator.value=='A100','Proxy refresh accelerator differs')
                _apply_proxy_info(session,match.runtime_proxy_info);state.store.add(session)
        safe_session = None if session is None else {k: getattr(session,k) for k in
            ['name','endpoint','accelerator','variant','machine_shape']}
        origins()
        return dict(raw=raw, assignments=assignments, session=safe_session)
    claim = c.read(Path(output)/'dispatch.claimed')
    c.need(claim['notebook_hash'] == reg['job_nonce'] and claim['expected_lease'] == reg['expected_lease']
           and claim['registration_sha256'] == reg['registration_sha256'], 'SDK permit differs')
    if mode == 'allocate':
        c.lease_guard(reg)
        c.need(nonce == reg['job_nonce'] == c.read(Path(output)/'allocation.claimed')['notebook_hash']
               and str(uuid.UUID(nonce)) == nonce and state.store.get(reg['session_name']) is None,
               'Sole persisted assignment UUID/session differs')
        c.save(Path(output)/'sdk-allocation.claimed', dict(notebook_hash=nonce))
        response = state.client.assign(uuid.UUID(nonce), variant=Variant.GPU,
                                       accelerator=Accelerator.A100, shape=Shape.STANDARD)
        owned = dict(name=reg['session_name'], endpoint=response.endpoint, accelerator=response.accelerator.value,
                     variant='GPU', machine_shape='STANDARD', notebook_hash=nonce)
        c.save(Path(output)/'owned-endpoint.json', owned)
        # Save proof before the private session. A later failure still permits teardown.
        info = response.runtime_proxy_info
        state.store.add(SessionState(name=reg['session_name'], endpoint=response.endpoint,
            accelerator=response.accelerator.value, variant='GPU', machine_shape='STANDARD',
            token=info.token, url=info.url, token_expires_at=info.expires_at()))
        Path(reg['cli_config_path']).chmod(0o600)
        return owned
    if mode == 'unassign':
        owned = c.read(Path(output)/'owned-endpoint.json')
        c.need(endpoint == owned['endpoint'] and owned['name'] == reg['session_name']
               and owned['notebook_hash'] == reg['job_nonce'], 'No exact owned endpoint proof')
        state.client.unassign(endpoint)
        session = state.store.get(reg['session_name'])
        if session is not None and session.endpoint == endpoint:
            state.store.remove(reg['session_name'])
        return dict(status='unassign_requested', endpoint=endpoint)
    owned = checked_session(reg, output)
    session = state.store.get(reg['session_name'])
    c.need(session is not None and session.endpoint == owned['endpoint'], 'SDK session ownership differs')
    c.need(remote == '/content/dodge064' or remote.startswith('/content/dodge064/'), 'Remote path escaped058')
    c.need('..' not in Path(remote).parts, 'Remote traversal forbidden')
    contents = ContentsClient(session)
    if mode == 'mkdir':
        c.need(remote in ['/content/dodge064','/content/dodge064/inputs','/content/dodge064/inputs/challenge'], 'Unregistered directory')
        contents._request('PUT', remote, json_data=dict(type='directory'))
    elif mode == 'read-json':
        allowed={'/content/dodge064/exports/preflight-exit.json','/content/dodge064/exports/build-exit.json','/content/dodge064/exports/stage-exit.json','/content/dodge064/exports/ready/900000.json'}
        c.need(remote in allowed,'Unregistered small receipt path')
        value=contents._request('GET',remote,params={'content':'1'})
        raw=value.get('content');c.need(value.get('format')=='text' and isinstance(raw,str) and len(raw)<=65536,'Small receipt format/size differs')
        return dict(status='complete',data=json.loads(raw))
    elif mode == 'put':
        c.need(remote in ['/content/dodge064/control.json','/content/dodge064/runtime-admission.json',
                           '/content/dodge064/cancel.requested'], 'Unregistered control path')
        put_text(contents, remote, Path(local).read_bytes())
    elif mode == 'upload':
        permitted = {a['remote']: (a['local'],a['sha256']) for a in reg['uploads']}
        permitted['/content/dodge064/registration.json'] = (reg['registration_local'],reg['registration_sha256'])
        c.need(remote in permitted and Path(local).resolve() == Path(permitted[remote][0]).resolve()
               and c.sha(local) == permitted[remote][1], 'Upload differs from frozen manifest')
        c.lease_guard(reg)
        contents.upload(local, remote)
    elif mode == 'download':
        c.need(remote in ['/content/dodge064/build-artifacts.tar','/content/dodge064/training-artifacts.tar',
                           '/content/dodge064/runtime/dodge_rl/_native.cpython-313-x86_64-linux-gnu.so'],
               'Unregistered artifact download')
        target = Path(local); partial = Path(str(target)+'.partial')
        c.need(target.parent.resolve() == Path(output).resolve() and not target.exists()
               and not partial.exists(), 'Existing/redirected download forbidden')
        # Reserve exclusively before ContentsClient opens its writer. Preserve
        # partial bytes on failure; never replace an earlier download.
        with partial.open('xb'):
            pass
        contents.download(remote, str(partial))
        with partial.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(partial, target); c._base.fsync_dir(target.parent)
        partial.unlink(); c._base.fsync_dir(target.parent)
    else:
        raise ValueError('Unknown SDK operation')
    origins()
    return dict(status='complete', operation=mode)


def main():
    parser = argparse.ArgumentParser()
    for key in ['plan','sha256','output','sdk']:
        parser.add_argument('--'+key, required=True)
    for key in ['nonce','endpoint','remote','local']:
        parser.add_argument('--'+key)
    args = parser.parse_args()
    try:
        c.need(c.sha(args.plan) == args.sha256, 'Plan hash differs')
        plan = c.read(args.plan)
        c.need(c.sha(plan['registration_path']) == plan['registration_sha256'], 'Registration changed')
        reg = c.read(plan['registration_path']); reg['registration_sha256'] = plan['registration_sha256']
        # Cleanup must remain usable when unrelated frozen inputs have changed.
        for path, digest in reg['coordinator_source_pins'].items():
            c.need(c.sha(path) == digest, 'Coordinator changed')
        c.need(c.sha(plan['review_path']) == plan['review_sha256'], 'Exact review changed')
        review = c.read(plan['review_path'])
        c.need(review['status'] == 'no_blocking_findings'
               and review['registration_sha256'] == plan['registration_sha256']
               and all(review['coordinator_source_pins'].get(p) == d
                       for p,d in reg['coordinator_source_pins'].items()), 'Exact source review absent')
        c.need(c.sha(plan['authority_path']) == reg['authority_sha256'] == plan['authority_sha256'],
               'Reviewed authority changed')
        if args.sdk=='control-server':
            serve_control(reg,args.output)
            return
        result = sdk_adapter(reg, args.output, args.sdk, nonce=args.nonce, endpoint=args.endpoint,
                             remote=args.remote, local=args.local)
        print(json.dumps(result, allow_nan=False))
    except BaseException as error:
        print(json.dumps(dict(status='SDK_failure',exception_type=type(error).__name__,http_status=getattr(getattr(error,'response',None),'status_code',None))))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
