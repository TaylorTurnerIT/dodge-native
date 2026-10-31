"""Locked offline Linux build and pre-import origin certificate, no constructors."""
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import sysconfig

import common as c
from receipts import write_stage

SOURCE_ROOT = Path(__file__).resolve().parent


def require_ELF_x86_64(path):
    with Path(path).open('rb') as stream: header = stream.read(64)
    c.need(len(header) == 64 and header[:6] == b'\x7fELF\x02\x01', 'Linux64 little-endian ELF required')
    kind, machine = struct.unpack('<HH', header[16:20])
    c.need(kind == 3 and machine == 62, 'x86_64 shared ELF required')


def inventory(root):
    root = Path(root)
    c.need(not any(path.is_symlink() for path in root.rglob('*')), 'Runtime symlink forbidden')
    return {path.relative_to(root).as_posix(): c.sha(path) for path in sorted(root.rglob('*')) if path.is_file()}


def verify_certificate(reg):
    cert = c.read(c.HERE / 'artifacts/native-build.json')
    for key in ('record', 'job_nonce', 'registration_sha256', 'payload_sha256'):
        c.need(cert.get(key) == reg[key], 'Build certificate identity differs')
    c.need(cert['schema'] == 'dodge_colab_training_stage_v1' and cert['stage'] == 'native_build'
           and cert['status'] == 'complete' and cert['native_games'] == cert['training_frames'] == 0
           and cert['trained_weights_saved'] is False, 'Build stage semantics differ')
    c.need(inventory(reg['runtime_root']) == cert['runtime_members'], 'Runtime inventory changed since build')
    c.need(cert['engine_source_manifest_sha256'] == c.sha(SOURCE_ROOT/'native_source_manifest.json'), 'Engine lineage changed')
    require_ELF_x86_64(cert['native_binary'])
    for path,digest in cert['linked_and_framework_libraries'].items():
        c.need(c.sha(path)==digest,'Certified native/framework shared library changed')
    return cert


def verify_loaded(cert):
    for name, module in list(sys.modules.items()):
        if name == 'dodge_rl' or name.startswith('dodge_rl.'):
            path = Path(module.__file__).resolve()
            relative = path.relative_to(cert['runtime_root']).as_posix()
            c.need(relative in cert['runtime_members'] and c.sha(path) == cert['runtime_members'][relative],
                   'Loaded runtime origin differs: ' + name)


def build_runtime(reg):
    c.check_lease(reg); c.verify_pins(reg)
    c.need(not (c.HERE/'build').exists(),'Old build output forbidden; no reuse/retry')
    artifacts = c.HERE/'artifacts'; artifacts.mkdir(exist_ok=False)
    for name in ('source-assembly.claimed','source-assembly.json'):
        c.need((c.HERE/name).is_file(),'Source assembly evidence absent')
        shutil.copyfile(c.HERE/name,artifacts/name)
    c.save(artifacts/'native-build.claimed', dict(record='DODGE-062', job_nonce=reg['job_nonce']))
    try:
        c.need(sys.platform == 'linux' and platform.machine() == 'x86_64' and sys.version_info[:2] == (3, 13),
               'Registered CPython3.13 Linux x86_64 build ABI required')
        import torch
        import numpy as np
        from numpy._core import _multiarray_umath
        candidate=c.read(SOURCE_ROOT/'python_runtime_candidate.json')
        paths=dict(python=sys.executable,torch_python=torch.__file__,torch_native=torch._C.__file__,
                   numpy_python=np.__file__,numpy_native=_multiarray_umath.__file__)
        package_origins={name:dict(path=str(Path(path).resolve()),sha256=c.sha(path)) for name,path in paths.items()}
        c.need(package_origins==candidate['package_origins'] and torch.__version__==candidate['torch']
               and np.__version__==candidate['numpy'] and torch.version.cuda==candidate['cuda_runtime'],
               'Candidate Python/Torch/NumPy runtime differs; no install/fallback permitted')
        source = SOURCE_ROOT/'native_source'
        expected = c.read(SOURCE_ROOT/'native_source_manifest.json')['files']
        c.need(inventory(source) == expected, 'Archived engine source members/content differ')
        import time
        began=time.monotonic()
        toolchain = reg.get('linux_toolchain')
        if toolchain is None:
            from toolchain_setup import prepare
            toolchain=prepare(reg,artifacts)
        for key in ('rustc', 'cargo'):
            c.need(c.sha(toolchain[key]) == toolchain[key+'_sha256'], 'Linux toolchain binary differs')
        version = subprocess.run([toolchain['rustc'], '-vV'], capture_output=True, text=True, check=True, timeout=15).stdout
        c.need('release: 1.97.1' in version and 'host: x86_64-unknown-linux-gnu' in version
               and 'commit-hash: 8bab26f4f68e0e26f0bb7960be334d5b520ea452' in version,
               'Exact Rust compiler release/commit/target differs')
        for name in ('home','tmp','cargo-home'):(c.HERE/'build'/name).mkdir(parents=True,exist_ok=True)
        env = dict(PATH=str(Path(toolchain['cargo']).parent)+':/usr/bin:/bin',HOME=str(c.HERE/'build/home'),LANG='C.UTF-8',
                   TMPDIR=str(c.HERE/'build/tmp'),CARGO_HOME=str(c.HERE/'build/cargo-home'),
                   CARGO_TARGET_DIR=str(c.HERE/'build/target'), CARGO_BUILD_JOBS='2',
                   CARGO_NET_OFFLINE='true', PYO3_PYTHON=sys.executable, RUSTC=toolchain['rustc'])
        command = [toolchain['cargo'], 'build', '--release', '--locked', '--offline', '-p', 'dodge-rl-env',
                   '--lib', '--features', 'extension-module', '--config', 'source.crates-io.replace-with="owned-vendor"',
                   '--config', 'source.owned-vendor.directory="'+reg['vendor_root']+'"']
        from build_process import run
        run(command,reg=reg,cwd=source,env=env,stdout=artifacts/'native-build.stdout',
            stderr=artifacts/'native-build.stderr',deadline=began+reg['native_setup_work_seconds'])
        c.check_lease(reg)
        runtime = Path(reg['runtime_root']); shutil.copytree(SOURCE_ROOT/'runtime', runtime)
        binary = runtime/'dodge_rl'/('_native'+sysconfig.get_config_var('EXT_SUFFIX'))
        shutil.copyfile(c.HERE/'build/target/release/libdodge_rl_env.so', binary)
        require_ELF_x86_64(binary)
        exports = subprocess.run(['nm', '-D', '--defined-only', str(binary)], capture_output=True,
                                 text=True, check=True, timeout=15).stdout
        c.need(any(line.split()[-1:] == ['PyInit__native'] for line in exports.splitlines()), 'PyO3 init symbol differs')
        linked=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,check=True,timeout=15).stdout
        c.need('not found' not in linked,'Unresolved Linux native shared library')
        libraries={}
        for line in linked.splitlines():
            for word in line.split():
                if word.startswith('/') and Path(word).is_file():
                    libraries[str(Path(word).resolve())]=c.sha(word)
        for directory in (Path(torch.__file__).parent,Path(np.__file__).parent,Path(np.__file__).parent.parent/'numpy.libs'):
            if directory.exists():
                for library in directory.rglob('*.so*'):
                    if library.is_file():libraries[str(library.resolve())]=c.sha(library)
        return write_stage(artifacts/'native-build.json', reg, 'native_build', 'complete',
            native_games=0, training_frames=0, trained_weights_saved=False,
            runtime_root=str(runtime), native_binary=str(binary), native_binary_sha256=c.sha(binary),
            runtime_members=inventory(runtime), engine_source_manifest_sha256=c.sha(SOURCE_ROOT/'native_source_manifest.json'),
            archived_MachO_sha256='ae9238670a0beea0951374562fcd5116013b7715b40be2bfc512ca242bdec7b7',
            rustc_version=version, toolchain=toolchain, Python=sys.version, interpreter_sha256=c.sha(sys.executable),
            EXT_SUFFIX=sysconfig.get_config_var('EXT_SUFFIX'), SOABI=sysconfig.get_config_var('SOABI'),
            package_origins=package_origins,package_versions=dict(torch=torch.__version__,numpy=np.__version__,CUDA=torch.version.cuda),
            linked_and_framework_libraries=libraries,ldd_output=linked,
            build_command=command, native_imports=0, constructor_calls=0,
            limits='Build/origin certificate only; no Linux engine behavioral or training qualification.')
    except BaseException as error:
        write_stage(artifacts/'native-build-first-failure.json', reg, 'native_build', 'failed',
                    native_games=0, training_frames=0, trained_weights_saved=False, error=repr(error))
        raise
