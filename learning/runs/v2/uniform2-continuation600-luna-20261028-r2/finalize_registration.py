"""Hash-only: copy an unchanged draft to registration-final.json after parent calibration acceptance."""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import binding as b


def finalize(draft_path, draft_sha, acceptance_path, acceptance_sha):
    b.need(b.sha(draft_path) == draft_sha and b.sha(acceptance_path) == acceptance_sha, 'finalize input SHA differs')
    draft = b.read(draft_path)
    b.need(draft['status'] == b.DRAFT_STATUS and draft['calibration']['parent_accepted'] is False, 'draft already finalized or not a draft')
    final = copy.deepcopy(draft)
    final['status'] = b.FINAL_STATUS
    final['calibration'].update(parent_accepted=True, parent_acceptance_path=str(Path(acceptance_path).resolve()),
                                parent_acceptance_sha256=acceptance_sha)
    final['input_pins'][str(Path(acceptance_path).resolve())] = acceptance_sha
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('draft', 'draft-sha256', 'calibration-acceptance', 'calibration-acceptance-sha256'):
        parser.add_argument('--'+name, required=True)
    a = parser.parse_args()
    final = finalize(a.draft, a.draft_sha256, a.calibration_acceptance, a.calibration_acceptance_sha256)
    b.validate_static(final)
    b.save(b.HERE/'registration-final.json', final)
    print(b.sha(b.HERE/'registration-final.json'), flush=True)
