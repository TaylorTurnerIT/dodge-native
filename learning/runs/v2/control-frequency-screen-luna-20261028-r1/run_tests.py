"""Run CPU-only synthetic screen and worker-to-terminal tests."""
import os,subprocess,sys
root=os.path.dirname(__file__);env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
for name in ('test_screen.py','test_worker_terminal.py'):
    code=subprocess.run([sys.executable,os.path.join(root,name)],env=env,check=False).returncode
    if code:raise SystemExit(code)
raise SystemExit(0)
