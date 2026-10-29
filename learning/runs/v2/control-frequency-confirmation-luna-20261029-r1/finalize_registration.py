"""Copy a draft to parent-registered form only after exact parent calibration acceptance."""
from __future__ import annotations
import argparse,copy
from pathlib import Path
import binding as b

def finalize(draft_path,draft_sha,acceptance_path,acceptance_sha):
    b.verify_pins({draft_path:draft_sha,acceptance_path:acceptance_sha})
    draft=b.read(draft_path);accept=b.read(acceptance_path)
    b.need(draft.get('status')=='source_review_pending' and draft.get('launch_authority') is False,'draft status differs')
    b.need(accept.get('schema')=='control_frequency_confirmation_parent_calibration_acceptance_v1' and accept.get('status')=='accepted' and accept.get('draft_sha256')==draft_sha and accept.get('source_manifest_sha256')==draft['source_manifest_sha256'],'parent calibration acceptance differs')
    final=copy.deepcopy(draft);final['status']='parent_registered';final['calibration_acceptance']={'path':str(Path(acceptance_path).resolve()),'sha256':acceptance_sha};final['input_pins'][str(Path(acceptance_path).resolve())]=acceptance_sha
    return final

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--draft',required=True);p.add_argument('--draft-sha256',required=True);p.add_argument('--acceptance',required=True);p.add_argument('--acceptance-sha256',required=True);a=p.parse_args()
    value=finalize(a.draft,a.draft_sha256,a.acceptance,a.acceptance_sha256);b.validate_static(value);b.save(b.HERE/'registration-final.json',value);print(b.sha(b.HERE/'registration-final.json'))
