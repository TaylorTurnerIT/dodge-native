"""Validate/render an inert registration draft; never grants launch authority."""
import json,sys
from pathlib import Path
TEMPLATE="{{"
def build(src,dst):
 d=json.loads(Path(src).read_text())
 if d.get("schema")!="paired_confirmed324_registration_v1" or d.get("status")!="parent_review_required_not_launchable": raise ValueError("draft identity/status invalid")
 if d.get("measured_references",{}).get("status")!="pending_notrun": raise ValueError("builder accepts only pending reference template")
 if any(TEMPLATE in json.dumps(d) for _ in (0,)): raise ValueError("template placeholders require parent binding")
 Path(dst).write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")
 return d
if __name__=="__main__": build(sys.argv[1],sys.argv[2])
