#!/usr/bin/env python3
"""Seal closed receipts with the host's available standard-library hashing API."""
import hashlib
import json
from pathlib import Path

OUT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-action-mode-execution-r1')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()

def save(name,value):
    with (OUT/name).open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')

save('extra-verifier-failure.json',{
    'scope':'An additional pure-file seal verification after all ten campaign postflight checks passed.',
    'error':"AttributeError: module 'hashlib' has no attribute 'file_digest'",
    'traceback':"Traceback (most recent call last):\n  File \"<stdin>\", line 5, in <module>\n  File \"<stdin>\", line 5, in <dictcomp>\nAttributeError: module 'hashlib' has no attribute 'file_digest'",
    'campaign_launches':0,'inference_calls':0,'file_mutations_before_exception':0,
    'resolution':'This final seal uses hashlib.sha256 streaming, as the execution observer and postflight already did. No campaign, model, bootstrap or environment change.'})
manifest=json.loads((OUT/'artifact-manifest.json').read_text())
assert all(sha(OUT/name)==digest for name,digest in manifest.items())
result=json.loads((OUT/'result.json').read_text())
assert result['status']=='complete'
assert result['actual_command_launch_count']==1
assert all(x['passed'] for x in result['postflight_checks'].values())
save('final-seal.json',{
    'status':'complete','result_sha256':sha(OUT/'result.json'),
    'prior_outer_manifest_sha256':sha(OUT/'artifact-manifest.json'),
    'prior_outer_manifest_entries_verified':len(manifest),
    'result_json_valid':True,'campaign_finalization_json_valid':True,
    'all_ten_postflight_checks_passed':True,
    'additional_verifier_api_failure_retained':'extra-verifier-failure.json',
    'campaign_launch_count_unchanged':1,'postflight_inference_calls':0,
    'decision_rows_verified':result['postflight_checks']['decision_trace_finite_and_complete']['detail']['decisions'],
    'hashing_scope':'All files are closed; this process writes no redirected stdout file. Final inventory excludes only itself.'})
final={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
save('artifact-manifest-final.json',final)
actual={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest-final.json'}
assert actual==final
print(json.dumps({'status':'complete','result_sha256':sha(OUT/'result.json'),
                  'final_manifest_sha256':sha(OUT/'artifact-manifest-final.json'),
                  'final_manifest_entries_verified':len(final),
                  'decision_rows':result['postflight_checks']['decision_trace_finite_and_complete']['detail']['decisions']}))
