"""Future owned-prefix Linux toolchain setup from exact official archive pins.

This module is source-prepared only. No installer runs during CPU preparation.
The parent's reviewed setup wall/financial authority must admit the build stage.
"""
from pathlib import Path
import os
import subprocess
import tarfile
import time
import urllib.request

import common as c


def prepare(reg, artifacts):
    pinned=c.read(Path(__file__).with_name('linux_toolchain_source.json'))
    root=c.HERE/'build/toolchain-inputs';root.mkdir(parents=True,exist_ok=False)
    prefix=c.HERE/'build/toolchain';prefix.mkdir()
    began=time.monotonic()
    def check():
        c.check_lease(reg)
        c.need(time.monotonic()-began<reg['native_setup_work_seconds'],'Native setup deadline')
    for name,component in pinned['components'].items():
        check();archive=root/(name+'.tar.xz')
        # One request per component, no retry or fallback toolchain.
        with urllib.request.urlopen(component['url'],timeout=15) as response, archive.open('xb') as output:
            while True:
                check();chunk=response.read(1024*1024)
                if not chunk:break
                output.write(chunk)
        c.need(c.sha(archive)==component['sha256'],'Official Linux toolchain archive differs')
        unpack=root/(name+'-unpacked');unpack.mkdir()
        with tarfile.open(archive,'r:xz') as source:source.extractall(unpack,filter='data')
        candidates=list(unpack.glob('*/install.sh'));c.need(len(candidates)==1,'Toolchain installer origin differs')
        from build_process import run
        run(['/bin/sh',str(candidates[0]),'--prefix='+str(prefix),'--disable-ldconfig'],
            reg=reg,cwd=candidates[0].parent,stdout=artifacts/(name+'-install.stdout'),
            stderr=artifacts/(name+'-install.stderr'),deadline=began+reg['native_setup_work_seconds'],
            env={'PATH':'/usr/bin:/bin','HOME':str(root),'LANG':'C.UTF-8'})
    check()
    return dict(rustc=str(prefix/'bin/rustc'),cargo=str(prefix/'bin/cargo'),
                rustc_sha256=c.sha(prefix/'bin/rustc'),cargo_sha256=c.sha(prefix/'bin/cargo'),
                official_component_pins=pinned['components'],installed_prefix=str(prefix))
