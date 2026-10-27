#!/usr/bin/env python3
"""Preparation receipts, invoked only after every redirected log is closed.

This command is stdlib-only. It creates no lease or campaign. The final artifact
manifest excludes only itself; implementation-result is written before it and
never mutated afterward. Console output is deliberately absent.
"""
from pathlib import Path
import ast
from datetime import datetime,timezone
import difflib
import json
import re
import sys
import long_d2 as c

HERE=Path(__file__).resolve().parent
ROOT=c.ORIGINAL_ROOT


def main():
    protected=c.read_json(HERE/'protected-before.json')
    after={k:c.sha(ROOT/k) for k in protected}
    c.save(HERE/'protected-after.json',after)
    changed=[k for k in protected if protected[k]!=after[k]]
    c.require(not changed,'Protected inputs changed: '+repr(changed))
    freeze=c.read_json(HERE/'freeze-receipt.json')
    preflight=c.pure_preflight(HERE/'capsule')
    c.require(preflight==freeze,'Frozen preflight receipt differs')
    testlog=HERE/'tests-final.log'
    text=testlog.read_text()
    m=re.search(r'Ran (\d+) tests in ([\d.]+)s\n\nOK\s*$',text)
    c.require(m is not None,'Final synthetic tests did not pass')
    negatives=c.read_json(HERE/'negative-control-receipt-r4.json')
    c.require(negatives['all_killed'] and negatives['base_controller_sha256']==c.sha(HERE/'long_d2.py'),
              'Negative controls do not match final controller')
    source_manifest={str(x.relative_to(HERE)):c.sha(x) for x in sorted(HERE.rglob('*.py'))
                     if 'capsule' not in x.relative_to(HERE).parts}
    c.save(HERE/'source-manifest.json',source_manifest)
    c.save(HERE/'test-receipt.json',dict(version='long_D2_synthetic_test_receipt_v1',
        positive_test_methods=int(m.group(1)),positive_test_seconds=float(m.group(2)),
        subtests_not_counted_as_separate_test_methods=True,
        command=[str(ROOT/'learning/.venv/bin/python'),'-B','-m','unittest','discover','-s',str(HERE),
                 '-p','test_long_d2.py','-v'],log_sha256=c.sha(testlog),
        test_source_sha256=c.sha(HERE/'test_long_d2.py'),controller_sha256=c.sha(HERE/'long_d2.py'),
        negative_controls=negatives['count'],all_negative_controls_assertion_failures=True,
        actual_supervisor_stdlib_fake_worker=True,fake_clocks=True,
        actual_teacher_native_MPS_gameplay_or_gradient_updates=False,
        historical312_or72_results_reused=False))
    reference=ROOT/'learning/runs/v2/postovernight-action-mode-prepare-r3/runner.py'
    patch=''.join(difflib.unified_diff(reference.read_text().splitlines(True),
                    (HERE/'long_d2.py').read_text().splitlines(True),
                    fromfile=str(reference.relative_to(ROOT)),tofile=str((HERE/'long_d2.py').relative_to(ROOT))))
    (HERE/'full-patch-vs-diagnostic-r3.diff').write_text(patch)
    # Exact copied reference functions are proven from source, never imported.
    def functions(path):
        source=path.read_text();lines=source.splitlines()
        return {n.name:'\n'.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno])
                for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
    old,new=functions(reference),functions(HERE/'long_d2.py')
    reused=['cancellation_signals','stop_owned','sampled_rss','self_peak']
    c.require(all(old[name]==new[name] for name in reused),'Copied reference helper changed')
    ledger_before=c.read_json(HERE/'ledger-observation-before.json')
    ledger_after=c.read_json(ROOT/'learning/runs/v2-orchestration/state.json')
    c.save(HERE/'ledger-observation-after.json',ledger_after)
    result=dict(version='long_D2_implementation_result_v1',status='prepared_for_parent_frozen_review_only',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),owned_directory=str(HERE),
        actual_training_or_gameplay_launched=False,actual_ML_native_imports_or_checkpoint_deserialization=False,
        active_lease_created=False,ledger_written=False,scheduler_changed=False,children_created=False,
        source_inputs_unchanged=75,protected_files_unchanged=len(protected),protected_changes=changed,
        parent_ledger_changes_outside_child_scope=ledger_before!=ledger_after,
        positive_test_methods=int(m.group(1)),negative_controls=negatives['count'],
        all_negative_controls_assertion_failures=True,
        frozen_identity_document_sha256=freeze['identity_document_sha256'],
        checkpoint_identity_semantic_sha256=freeze['checkpoint_identity_semantic_sha256'],
        capsule_manifest_sha256=freeze['capsule_manifest_sha256'],
        controller_sha256=c.sha(HERE/'long_d2.py'),protocol_sha256=c.PROTOCOL_SHA256,
        config_document_sha256=c.CONFIG_SHA256,source_manifest_sha256=c.sha(HERE/'source-manifest.json'),
        test_receipt_sha256=c.sha(HERE/'test-receipt.json'),
        required_lease='required-lease.json',exact_invocation='invocation.json',
        pure_preflight='pure-preflight-cli.json',capsule_path=str(HERE/'capsule'),
        reference_runner_sha256=c.sha(reference),reference_functions_copied_byte_identically=reused,
        full_patch='full-patch-vs-diagnostic-r3.diff',full_patch_sha256=c.sha(HERE/'full-patch-vs-diagnostic-r3.diff'),
        artifact_inventory='artifact-manifest-final.json',inventory_captured_after_redirected_stdout_closed=True,
        limitations=[
          'No actual teacher/native/MPS runtime, parent tensor restore, gameplay, PPO or campaign validation occurred.',
          'Legacy check_frozen and validate_transition are executed unchanged only in the real owned worker; preparation verified their input bytes and synthetic rejection paths.',
          'OS/MPS throughput, memory growth and entry determinism remain unverified until the separately reviewed one-shot run.',
          'Cooperative resource sampling can be delayed by blocked native/MPS calls; the independent supervisor enforces its absolute deadline.',
          'Terminal wall observations exclude their own write and process exit; the parent must observe actual exit/wall.',
          'Early development attempts retained logs; their source reconstructions are explicitly labeled, not claimed as contemporaneous snapshots.'
        ])
    c.save(HERE/'implementation-result.json',result)
    inventory={str(x.relative_to(HERE)):c.sha(x) for x in sorted(HERE.rglob('*'))
               if x.is_file() and x.name!='artifact-manifest-final.json'}
    c.save(HERE/'artifact-manifest-final.json',dict(version='long_D2_preparation_artifacts_v1',files=inventory,
              excludes=['artifact-manifest-final.json'],all_redirected_logs_closed=True))
    for relative,digest in inventory.items():
        c.require(c.sha(HERE/relative)==digest,'Final inventory drift: '+relative)


if __name__=='__main__':main()
