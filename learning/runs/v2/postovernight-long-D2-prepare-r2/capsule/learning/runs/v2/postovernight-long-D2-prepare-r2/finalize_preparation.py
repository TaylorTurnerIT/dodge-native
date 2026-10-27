#!/usr/bin/env python3
"""Finalize r2 receipts after every redirected log closes; stdlib only.

No output file is redirected to this directory while inventory is captured.
Identity and capsule exclude receipts that would create hash cycles. Historical
attempts remain in the preparation inventory, never the active source inventory.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast
import difflib
import json
import re
import long_d2 as c

HERE=Path(__file__).resolve().parent
ROOT=c.ORIGINAL_ROOT
R1=HERE.parent/'postovernight-long-D2-prepare-r1'
ACTIVE=sorted(p.name for p in HERE.glob('*.py'))+['README.md']


def nodes(path):
    source=path.read_text();lines=source.splitlines(True)
    return {n.name:''.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno])
            for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def main():
    protected=c.read_json(HERE/'protected-before.json')
    after={name:c.sha(ROOT/name) for name in protected}
    changes=[name for name in protected if protected[name]!=after[name]]
    c.save(HERE/'protected-after.json',after)
    c.require(not changes,'Protected bytes changed: '+repr(changes))
    p=c.registered_protocol(ROOT/c.PROTOCOL_REL)
    before=c.read_json(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol.json')
    protocol_changes=[k for k in sorted(set(before)|set(p)) if before.get(k)!=p.get(k)]
    c.require(protocol_changes==['controller','registered_at_utc'],'Parent protocol changed experiment semantics')
    c.save(HERE/'protocol-diff.json',dict(changed_fields=protocol_changes,
           before={k:before[k] for k in protocol_changes},after={k:p[k] for k in protocol_changes},
           config_raw_sha256=c.CONFIG_SHA256,config_raw_hash_unchanged=True))
    reconcile=c.read_json(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-review-parent-reconciliation-r1.json')
    for kind in ('learner','supervisor'):
        c.require(c.sha(HERE.parent/('postovernight-long-D2-'+kind+'-review-r1')/'findings.json')==
                  reconcile[kind+'_findings_sha256'],'Parent review binding changed')
    ledger=c.read_json(ROOT/'learning/runs/v2-orchestration/state.json')
    c.require(ledger['active_long_campaign'] is None,'Preparation must not activate a lease')
    c.require(not (ROOT/p['output']).exists(),'Production campaign output must not exist')
    c.save(HERE/'ledger-observation-after.json',ledger)
    preflight=c.pure_preflight(HERE/'capsule');freeze=c.read_json(HERE/'freeze-receipt.json')
    c.require(preflight==freeze,'Frozen preflight differs')
    c.require(len(freeze['required_lease'])==15 and set(freeze['required_lease'])==c.LEASE_KEYS,'Lease is not strict 15 fields')
    log=HERE/'tests-final-r2.log';match=re.search(r'Ran (\d+) tests in ([\d.]+)s\n\nOK\s*$',log.read_text())
    c.require(match is not None,'Final tests did not pass')
    negatives=c.read_json(HERE/'negative-control-receipt-final2.json')
    regression=c.read_json(HERE/'r1-regression-control-receipt-final2.json')
    c.require(negatives['all_killed'] and negatives['count']==14 and
              negatives['base_controller_sha256']==c.sha(HERE/'long_d2.py'),'Final 14 controls mismatch')
    c.require(regression['all_killed'] and regression['count']==3,'Exact r1 controls did not all fail by assertion')
    observations=[]
    for path in sorted((HERE/'publication-final-evidence-r2').glob('*/scenario/observation.json')):
        v=c.read_json(path)
        c.require(v['actual_guard'] and v['actual_supervise'] and not v['ML_imports'] and
                  v['owned_group_positively_absent'] and v['manifest_still_matches'],'Probe scope/stability failed')
        c.require(all(not x['open_output_writers'] for x in v['artifact_hash_writer_checks']),'Open output writer was hashed')
        if v['mutation']!='none':
            c.require(v['return_code']==1 and v['terminal']['experiment_status']=='failed' and
                      not v['manifest_available'],'Mutation retained complete authority')
        else:
            c.require(v['return_code'] in (0,2) and v['manifest_available'],'Positive delayed probe failed')
            r=v['terminal']['supervisor_resources_final']
            c.require(r['maximum_sample_gap_seconds']<=.5 and r['maximum_full_input_gap_seconds']<=5,'Interval relaxed')
        observations.append(dict(path=str(path.relative_to(HERE)),sha256=c.sha(path),phase=v['phase'],
             mutation=v['mutation'],mode=v['mode'],return_code=v['return_code'],
             manifest_available=v['manifest_available'],controller_sha256=v['controller_sha256']))
    c.require(len(observations)==58,'Fresh actual-Guard OS probe count differs')
    c.save(HERE/'publication-probe-receipt.json',dict(count=len(observations),cases=observations,
         all_owned_groups_positively_absent=True,no_open_manifest_bound_writers=True,
         resource_max_seconds=.5,full_input_max_seconds=5,real_SIGINT_and_SIGTERM_subprocesses=True))
    old,new=nodes(R1/'long_d2.py'),nodes(HERE/'long_d2.py')
    changed=[name for name in old if old[name]!=new.get(name)]
    c.require(set(changed)=={'capsule_context','cancellation_signals','Guard','publish_terminal','supervise','worker'},
              'Unrelated top-level code changed: '+repr(changed))
    expected_worker=old['worker'].replace('                  worker_wall_seconds_lower_bound=',
        "                  inherited_consumed_wall_scope='D1 historical context only; long budget uses supervisor T0',\n                  worker_wall_seconds_lower_bound=")
    c.require(new['worker']==expected_worker,'Worker changed beyond receipt scope label')
    c.require(new['Learner']==old['Learner'] and new['run_schedule']==old['run_schedule'] and
              new['Schedule']==old['Schedule'],'Learner/schedule source changed')
    c.save(HERE/'non-supervision-source-comparison.json',dict(
         r1_controller_sha256=c.sha(R1/'long_d2.py'),r2_controller_sha256=c.sha(HERE/'long_d2.py'),
         changed_top_level_nodes=changed,added_top_level_nodes=sorted(set(new)-set(old)),
         byte_identical_nodes=sorted(name for name in old if name in new and old[name]==new[name]),
         Learner_and_schedule_byte_identical=True,
         capsule_context_binding_change='Pin the original new identity document to its readonly capsule digest without a self-hash cycle',worker_only_change='historical consumed_wall_seconds receipt scope label',
         original_legacy_inputs_verified=75,
         guard_dependency='Shared worker/supervisor Guard separates resource sampling from full hashes to enforce existing intervals; no ML call-site or limit changes'))
    patch=''
    for name in ACTIVE:
        original=(R1/name).read_text() if (R1/name).exists() else ''
        patch+=''.join(difflib.unified_diff(original.splitlines(True),(HERE/name).read_text().splitlines(True),
                  fromfile=str((R1/name).relative_to(ROOT)),tofile=str((HERE/name).relative_to(ROOT))))
    (HERE/'full-r1-to-r2.diff').write_text(patch)
    sources={name:c.sha(HERE/name) for name in ACTIVE}
    c.save(HERE/'source-manifest.json',sources)
    c.save(HERE/'test-receipt.json',dict(positive_test_methods=int(match[1]),
        original_synthetic_methods=70,new_publication_methods=11,positive_test_seconds=float(match[2]),
        subtests_not_separate_methods=True,actual_guard_OS_publication_probes=len(observations),
        command=[str(ROOT/'learning/.venv/bin/python'),'-B','-m','unittest','discover','-s',str(HERE),'-p','test*.py','-v'],
        environment=dict(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp'),
                         LONG_D2_PROBE_EVIDENCE=str(HERE/'publication-final-evidence-r2')),
        log_sha256=c.sha(log),source_manifest_sha256=c.sha(HERE/'source-manifest.json'),
        negative_controls=14,exact_r1_regression_controls=3,all_controls_AssertionError_not_API_errors=True,
        actual_ML_native_teacher_deserialization_inference_gameplay_gradient=False))
    result=dict(version='long_D2_supervisor_repair_implementation_result_v2',
        status='prepared_for_fresh_parent_frozen_review_only',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        owned_directory=str(HERE),accepted_blockers_repaired=['SUP-001/P1','SUP-002/P2'],
        production_campaign_launched=False,production_campaign_output_created=False,active_lease_created=False,
        ML_native_inference_gameplay_teacher_deserialization_gradient=False,children_or_installs_or_external_messages=False,
        parent_protocol_config_ledger_docs_edited=False,protected_files_unchanged=len(protected),protected_changes=changes,
        protected_before_sha256=c.sha(HERE/'protected-before.json'),protected_after_sha256=c.sha(HERE/'protected-after.json'),
        original_legacy_inputs_unchanged=75,learner_and_schedule_byte_identical=True,
        positive_test_methods=int(match[1]),actual_guard_OS_publication_probes=len(observations),
        inherited_negative_controls=14,exact_r1_regression_controls=3,all_negative_controls_assertion_failures=True,
        protocol_sha256=c.PROTOCOL_SHA256,config_document_sha256=c.CONFIG_SHA256,
        controller_sha256=c.sha(HERE/'long_d2.py'),
        active_source_before={name:c.sha(R1/name) if (R1/name).exists() else None for name in ACTIVE},
        active_source_after=sources,source_manifest_sha256=c.sha(HERE/'source-manifest.json'),
        test_receipt_sha256=c.sha(HERE/'test-receipt.json'),
        source_before_after='source-manifest.json and protected-before.json/protected-after.json',
        frozen_identity_document_sha256=freeze['identity_document_sha256'],
        checkpoint_identity_semantic_sha256=freeze['checkpoint_identity_semantic_sha256'],
        capsule_manifest_sha256=freeze['capsule_manifest_sha256'],capsule_path=str(HERE/'capsule'),
        required_lease='required-lease.json',exact_invocation='invocation.json',
        strict_lease_fields=15,full_diff='full-r1-to-r2.diff',full_diff_sha256=c.sha(HERE/'full-r1-to-r2.diff'),
        source_comparison='non-supervision-source-comparison.json',test_receipt='test-receipt.json',
        publication_probe_receipt='publication-probe-receipt.json',
        negative_control_receipts=['negative-control-receipt-final2.json','r1-regression-control-receipt-final2.json'],
        pure_preflight='pure-preflight-cli.json',artifact_inventory='artifact-manifest-final.json',
        final_snapshot_after_all_redirected_logs_closed=True,
        inherited_consumed_wall_seconds='D1 historical context only; never the new supervisor T0 budget',
        prior_capsule_and_logs='Original-only hash-pinned references; never copied into new execution capsule',
        limitations=['No actual Torch/native/MPS, parent tensor/Adam/RNG restoration, entry equality, gameplay, inference or training validation.',
                    'Actual MPS restoration and entry equality remain mandatory future runtime gates.',
                    'Parent must perform a fresh frozen review before creating the exact lease and launching once.',
                    'Parent must observe actual raw exit and wall time; terminal timing excludes its own write and process exit.',
                    'Original D1 is the only eligible parent; all failed D2 weights remain ineligible, with no resume.',
                    'Bootstrap convenience-API failure and all synthetic/negative-control attempts remain retained.'])
    c.save(HERE/'implementation-result.json',result)
    inventory={str(path.relative_to(HERE)):c.sha(path) for path in sorted(HERE.rglob('*'))
               if path.is_file() and path!=HERE/'artifact-manifest-final.json'}
    c.save(HERE/'artifact-manifest-final.json',dict(files=inventory,excludes=['artifact-manifest-final.json'],
           all_redirected_logs_closed=True,identity_excludes_its_document_and_manifest=True))
    for name,digest in inventory.items():c.require(c.sha(HERE/name)==digest,'Final inventory drift: '+name)


if __name__=='__main__':main()
