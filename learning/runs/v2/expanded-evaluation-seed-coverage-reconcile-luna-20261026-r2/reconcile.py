#!/usr/bin/env python3
"""Read-only metadata reconciliation for the six proposed D2 ancestors.
Uses only JSON/JSONL and hashes; never opens checkpoint payloads or runtime modules.
"""
import hashlib, json, pathlib
ROOT=pathlib.Path('learning/runs/v2')
OUT=ROOT/'expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2'
PROPOSAL=ROOT/'expanded-evaluation-registration-proposal-parent-20261026-r2/proposal.json'
p=json.loads(PROPOSAL.read_text())
rows=[]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
for c in p['candidates']:
    cp=pathlib.Path(c['checkpoint_path']); receipt=pathlib.Path(c.get('source_receipt_path',c.get('source_audit_path')))
    # Receipt/audit provenance only. Candidate 348's full audit is nested; its exact
    # bound terminal parent receipt is identified by proposal and registration.
    d=json.loads(receipt.read_text())
    run=pathlib.Path('learning/runs/v2')/cp.parent.name
    wrp=run/'worker-result.json'
    wr=json.loads(wrp.read_text()) if wrp.exists() else {}
    episode=run/'training-episodes.jsonl'
    journal_sha=sha(episode) if episode.exists() else None
    indices=d.get('next_episode_indices',wr.get('final_resume_next_episode_indices'))
    counters=d.get('cumulative_counters',d.get('candidate_cumulative_counters',wr.get('cumulative_counters')))
    rows.append({'phase_update':c['phase_update'],'run_id':d.get('run_id',cp.parent.name),'candidate_exact_path':str(cp),'candidate_sha256_expected':c['checkpoint_sha256'],'receipt_or_audit_path':str(receipt),'receipt_or_audit_sha256':sha(receipt),'config_sha256':d.get('config_sha256'),'episode_journal_path':str(episode) if episode.exists() else None,'episode_journal_sha256':journal_sha,'episode_journal_present':episode.exists(),'next_episode_indices_count':len(indices) if isinstance(indices,list) else None,'next_episode_indices_min':min(indices) if isinstance(indices,list) else None,'next_episode_indices_max':max(indices) if isinstance(indices,list) else None,'counters':counters,'candidate_parent_checkpoint_sha256':d.get('candidate_parent_checkpoint_sha256',d.get('parent_checkpoint_sha256')),'parent_receipt_sha256':d.get('parent_terminal_receipt_sha256'),'seed_or_master_seed_fields':{k:v for k,v in d.items() if 'seed' in k.lower() or 'master' in k.lower()},'ancestry_status':'receipt hash link available; complete seed identity unavailable in receipt fields'})
# fixture provenance: hash and inspect bytes as text only; malformed line is synthetic fixture.
f=ROOT/'postovernight-long-D2-boundary-review-r3/inner-publication-fixture-r2/execution/inner-verification.jsonl'
fixture={'path':str(f),'sha256':sha(f),'bytes':f.stat().st_size,'first_line_hex':f.read_bytes().splitlines()[0][:96].hex(),'owning_fixture_manifest_present':False}
(OUT/'reconciliation.json').write_text(json.dumps({'schema':'expanded_eval_seed_coverage_reconciliation_v1','proposal_sha256':sha(PROPOSAL),'cohorts_unchanged':p['cohorts'],'ancestors':rows,'fixture_parse_error':fixture,'coverage_conclusion':'No collision found in prior audit logged subset. Full exclusion proof unavailable: receipts expose next indices and counters but not immutable original environment master-seed identities or a complete closed set of environment constructions for every completed, abandoned, and in-flight attempt. Candidate copy paths are not substituted for proposal exact original paths. B/E outcomes remain unopened.','minimal_missing_artifacts':['Per original run, parent-accepted registration/config JSON tying exact original checkpoint identity to original environment master seed and frozen SplitMix64 implementation/source hash.','Closed, receipt-hash-linked construction/attempt inventory covering completed, abandoned, and in-flight jobs, with each construction start/end episode-index bounds and termination disposition.','For candidate 348, parent finalization receipt and its complete registered ancestor receipt chain; current proposal cites full-audit, not parent terminal acceptance.','Source proof that every original journal row and every construction index range is represented exactly once, with journal hashes reconciled to accepted receipts.'],'prohibitions_observed':['No checkpoint binary reads','No B/E outcome opens','No registry/reservation/lease/gate/launch mutation']},indent=2,sort_keys=True)+'\n')
print(OUT/'reconciliation.json')
