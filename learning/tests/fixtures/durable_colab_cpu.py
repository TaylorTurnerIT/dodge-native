"""CPU ONLY stand-ins for remote GPU work; production registration rejects these."""
import hashlib,io,json,os,sys,tarfile,time
from pathlib import Path


def setup():
    source=Path(os.environ['DURABLE_FIXTURE_SOURCE']);sys.path[:0]=[str(source),str(source/'runtime'),str(source/'source_tests')]
    import common as c
    reg=json.loads(Path(os.environ['DURABLE_FIXTURE_REG']).read_text());reg['registration_sha256']=c.sha(os.environ['DURABLE_FIXTURE_REG'])
    return source,c,reg


def worker():
    source,c,reg=setup()
    import types
    from run_ray_source_checks import NoNative
    sys.meta_path.insert(0,NoNative())
    package=types.ModuleType('dodge_rl');package.__path__=[str(source/'runtime/dodge_rl')];sys.modules['dodge_rl']=package
    import worker as w
    from test_training_control import DummySession
    def load(path,sha):
        assert c.sha(path)==sha==reg['registration_sha256'];return dict(reg)
    c.load_registration=load;w.LiveSession=DummySession
    return w.main()


def stage(stage):
    source,c,reg=setup()
    from result_safety.remote_stage import run_stage_child
    from result_safety.custody import durable_new,canonical
    from safety_hooks import preflight_export,terminal_export
    # The real wrapper owns a real child and status receipt. Only GPU/runtime
    # execution is replaced; all custody, writer, archive and ACK code is real.
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'program',stage]
    def exported():
        if stage=='preflight':return preflight_export(reg)
        if stage=='build':return dict(sha256=c.sha(c.HERE/'build-artifacts.tar'),manifest=dict(sequence=0))
        return terminal_export(reg)
    result=run_stage_child(command,c.HERE/'stages'/stage,reg,guard=lambda:c.check_lease(reg),seconds=60,
           terminal_export=exported,failure_export=(lambda:terminal_export(reg,failure=True)) if stage=='train' else None)
    durable_new(c.HERE/'exports'/('stage-exit.json' if stage=='train' else stage+'-exit.json'),canonical(result))
    return 0 if result['status']=='complete' else 1


def program(stage):
    source,c,reg=setup()
    from safety_hooks import preflight
    if stage=='preflight':
        for item in reg['storage_challenge']['chunks']:
            item['remote']=str(c.HERE/Path(item['remote']).relative_to('/content/dodge064'))
        preflight(reg);return 0
    if stage=='build':
        artifacts=c.HERE/'artifacts';artifacts.mkdir()
        body=dict(native_binary_sha256='0'*64,fixture_only=True)
        data=json.dumps(body).encode()
        with tarfile.open(c.HERE/'build-artifacts.tar','x') as archive:
            item=tarfile.TarInfo('native-build.json');item.size=len(data);archive.addfile(item,io.BytesIO(data))
        return 0
    import remote_entry
    actual_decoder=remote_entry.decode_archive
    remote_entry.decode_archive=lambda path,sha,reg,**kw:actual_decoder(path,sha,reg,allow_fixtures=True,**kw)
    run_campaign=remote_entry.run_campaign
    from supervisor import supervise
    from test_training_control import live_dummy
    jobfail=os.environ.get('DURABLE_FIXTURE_FAIL_JOB')
    def supervisor(command,out,reg,job,check_control):
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'worker',
                 '--registration',os.environ['DURABLE_FIXTURE_REG'],'--sha256',reg['registration_sha256'],'--job',job['id']]
        if job['id']==jobfail:command=[sys.executable,'-B','-c','raise SystemExit(7)']
        return supervise(command,out,reg,job,check_control=check_control,resource_probe=live_dummy,
            GPU_probe=lambda _:0,exit_probe=lambda child:child.poll() is not None,qualified_linux=False,sample_seconds=.01)
    result=run_campaign(reg,os.environ['DURABLE_FIXTURE_REG'],reg['registration_sha256'],supervisor=supervisor)
    return 0 if result['status']=='complete' else 1


if __name__=='__main__':
    mode=sys.argv.pop(1)
    if mode=='worker':raise SystemExit(worker())
    if mode=='stage':raise SystemExit(stage(sys.argv[1]))
    raise SystemExit(program(sys.argv[1]))
