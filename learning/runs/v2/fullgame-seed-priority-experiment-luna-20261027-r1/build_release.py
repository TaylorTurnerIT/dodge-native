"""One bounded offline release build into owned cache/target, never installation."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TOOLCHAIN = Path('/Users/taylor/.rustup/toolchains/1.97.1-aarch64-apple-darwin/bin')
record = HERE/'logs/release-build.json'
if record.exists() or (HERE/'logs/release-build.log').exists():
    raise FileExistsError('Preserve first build attempt; use a successor for a new attempt')
argv = [str(TOOLCHAIN/'cargo'),'rustc','--release','--locked','--offline','-p','dodge-rl-env','--lib','--features','extension-module','--','-C','link-arg=-undefined','-C','link-arg=dynamic_lookup']
env = dict(CARGO_BUILD_JOBS='2',CARGO_NET_OFFLINE='true',CARGO_HOME=str(HERE/'native/cargo-home'),CARGO_TARGET_DIR=str(HERE/'native/target'),PYO3_PYTHON=str(ROOT/'python/.venv/bin/python3.12'),PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(HERE/'empty-pycache'),TMPDIR=str(HERE/'native/tmp'),RUSTC=str(TOOLCHAIN/'rustc'),RUSTDOC=str(TOOLCHAIN/'rustdoc'),RUSTFMT=str(TOOLCHAIN/'rustfmt'))
started=time.monotonic(); result=dict(argv=argv,cwd=str(HERE/'native/source'),environment_overrides=env,wall_limit_seconds=300,profile='release',installed=False)
with (HERE/'logs/release-build.log').open('x') as log:
    try:
        run=subprocess.run(argv,cwd=HERE/'native/source',env={**os.environ,**env},stdout=log,stderr=subprocess.STDOUT,timeout=300)
        result.update(exit_code=run.returncode,timed_out=False)
    except subprocess.TimeoutExpired:
        result.update(exit_code=None,timed_out=True)
result['wall_seconds']=time.monotonic()-started
record.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
if result['exit_code']==0:
    source=HERE/'native/target/release/lib_native.dylib'
    if not source.exists():
        source=HERE/'native/target/release/libdodge_rl_env.dylib'
    destination=HERE/'runtime/dodge_rl/_native.cpython-312-darwin.so'
    shutil.copyfile(source,destination)
    manifest=dict(status='built_not_runtime_qualified',profile='release',sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),bytes=destination.stat().st_size,path=str(destination),source_manifest='accepted_R2_exact_owned_copy',old_debug_artifact_used=False,release_parity_qualified=False,installed=False)
else:
    manifest=dict(status='release_build_gate_pending',profile='release',sha256=None,path=None,installed=False)
(HERE/'binary-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps(result));print(json.dumps(manifest))
