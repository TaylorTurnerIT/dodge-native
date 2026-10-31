"""One bounded persistent subprocess for control PUTs; no allocation or retry.

The pipe protocol and timing journal contain no credentials or proxy URLs.
Any timeout, malformed response or child loss permanently poisons this client.
"""
import json
import os
import select
import signal
import subprocess
import threading
import time


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'


class Clock:
    def __init__(self):
        self.wall=time.time();self.monotonic=time.monotonic();self.last=0.
    def now(self):
        self.last=max(self.last,time.time()-self.wall,time.monotonic()-self.monotonic)
        return self.last


def event(path, actor, phase, **fields):
    row=dict(actor=actor,phase=phase,utc_seconds=time.time(),**fields)
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    try:
        os.write(fd,encoded(row));os.fsync(fd)
    finally:os.close(fd)


def reap(process):
    if process.poll() is None:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
    else:process.wait()
    for stream in [process.stdin,process.stdout]:
        if stream is not None:stream.close()


class PipeClient:
    def __init__(self,command,env,journal,expected_ready,*,startup_timeout=15):
        self.lock=threading.Lock();self.poisoned=False;self.sequence=0
        self.clock=Clock();self.buffer=b'';self.journal=journal;self.process=None
        event(journal,'parent','startup_begin')
        try:
            self.process=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,start_new_session=True,bufsize=0)
            os.set_blocking(self.process.stdin.fileno(),False)
            os.set_blocking(self.process.stdout.fileno(),False)
            ready=self.read_line(self.clock.now()+startup_timeout)
            if ready!=expected_ready:raise ValueError('Control startup identity differs')
            event(journal,'parent','startup_ready',child_pid=self.process.pid)
        except BaseException as error:
            self.abort('startup_failure',error);raise

    def remaining(self,deadline):
        left=deadline-self.clock.now()
        if left<=0:raise TimeoutError('Control channel deadline')
        return left

    def read_line(self,deadline):
        while b'\n' not in self.buffer:
            left=self.remaining(deadline)
            ready,_,_=select.select([self.process.stdout],[],[],left)
            self.remaining(deadline)
            if not ready:raise TimeoutError('Control channel deadline')
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk:raise EOFError('Control child exited')
            self.buffer+=chunk
            if len(self.buffer)>65536:raise ValueError('Control response too large')
        line,self.buffer=self.buffer.split(b'\n',1)
        self.remaining(deadline)
        return json.loads(line)

    def abort(self,phase,error):
        self.poisoned=True
        try:event(self.journal,'parent',phase,exception_type=type(error).__name__)
        finally:
            if self.process is not None:
                reap(self.process)
                event(self.journal,'parent','closed',child_pid=self.process.pid,child_returncode=self.process.returncode,directly_reaped=True,after_failure=True)

    def request(self,remote,content,*,timeout=8):
        with self.lock:
            if self.poisoned:raise ValueError('Control channel permanently closed')
            self.sequence+=1;identifier=self.sequence;deadline=self.clock.now()+timeout
            try:
                data=encoded(dict(id=identifier,remote=remote,content=content.decode('utf-8')))
                if len(data)>65536:raise ValueError('Control request too large')
                event(self.journal,'parent','request_begin',request_id=identifier)
                offset=0
                while offset<len(data):
                    left=self.remaining(deadline)
                    _,ready,_=select.select([],[self.process.stdin],[],left)
                    self.remaining(deadline)
                    if not ready:raise TimeoutError('Control channel deadline')
                    offset+=os.write(self.process.stdin.fileno(),data[offset:])
                response=self.read_line(deadline)
                if response!={'id':identifier,'status':'complete'}:
                    raise ValueError('Control response identity/status differs')
                event(self.journal,'parent','request_complete',request_id=identifier)
            except BaseException as error:
                self.abort('request_failure',error);raise

    def close(self):
        with self.lock:
            if not self.poisoned:
                self.poisoned=True;reap(self.process)
                event(self.journal,'parent','closed',child_pid=self.process.pid,
                      child_returncode=self.process.returncode,directly_reaped=True)


def serve(handler,ready,journal,*,input_stream,output_stream):
    """One response per request. First failure ends the service without restart."""
    output_stream.write(encoded(ready));output_stream.flush();last=0
    while True:
        line=input_stream.readline(65537)
        if not line:return
        identifier=None
        try:
            if len(line)>65536 or not line.endswith(b'\n'):raise ValueError('Invalid request framing')
            request=json.loads(line);identifier=request['id']
            if type(identifier) is not int or identifier!=last+1:raise ValueError('Request sequence differs')
            last=identifier
            event(journal,'worker','request_received',request_id=identifier)
            handler(request)
            output_stream.write(encoded(dict(id=identifier,status='complete')));output_stream.flush()
        except BaseException as error:
            event(journal,'worker','request_failure',request_id=identifier,exception_type=type(error).__name__)
            output_stream.write(encoded(dict(id=identifier,status='failure')));output_stream.flush()
            return
