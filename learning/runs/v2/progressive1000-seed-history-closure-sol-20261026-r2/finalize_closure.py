"""Seal owned audit artifacts and exact input pins. No runtime execution."""
import collections
import hashlib
import json
from pathlib import Path
import re

import discover as io

HERE,ROOT=io.HERE,io.ROOT

def load(name):return json.loads((HERE/name).read_bytes())
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    paths=load('r1-unresolved-path-closure.json')['paths']
    collision=load('cohort-collision-check.json')
    gapgroups=collections.defaultdict(list)
    for row in paths:
        if row['status'].startswith('unresolved'):gapgroups[row['path'].split('/')[3]].append(row['path'])
    gaps=[]
    archives={
        'milestone1-r1':'source.tar.gz + source-manifest.json + benchmark-receipt.json + test-workspace.json',
        'milestone1-r2':'source.tar.gz + source-manifest.json + checks.json + benchmark-provenance.json',
        'milestone2-binding-r1':'source-final.tar.gz + inputs.tar.gz + owned-source-manifest.json + commands.jsonl',
        'milestone2-core-r1':'source.tar.gz + before-owned-source.tar.gz + before-source-manifest.json + commands.jsonl',
        'milestone2-math-r1':'source-manifest.json + input-manifest.json + commands.jsonl',
        'milestone2-wrapper-r1':'source.tar.gz + input-manifest.json + commands.jsonl; finite trajectory already covered separately'}
    for group,files in gapgroups.items():
        if group=='gate-baselines-r1':
            needed='Parent-issued outcome-free receipt binding gate-baselines-r1 d1/d3 native constructors to exact explicit seed ranges and attempt count. Include seed mode, worker/source identity and failed-start/reset allowance; do not open qualification outcomes.'
            available='28 path names/stat metadata only; outcome content deliberately not used. B/E reserved ranges are included as possible fixed lists, not observations.'
        else:
            needed=f'Finish command-to-test-source attribution from learning/runs/v2/{group}/{archives[group]}. For every selected native/Python test entrypoint, list actual constructor seed mode, master or explicit list, slot/index limits, custom singleton exclusions and recovery-reset count. Pin archived members and original command/raw exit. Do not substitute a source-name heuristic or successful test count for finite construction bounds.'
            available='Seed-only archived constructor-site excerpts recovered in archived-constructor-sites.json. Fixed headless profile seeds 1000..1064 and wrapper trajectory stream are covered; the entire selected native test inventory is not closed.'
        gaps.append({'id':group,'status':'unresolved','path_count':len(files),'paths':files,
                     'available_evidence':available,'precisely_needed_artifact_or_action':needed,
                     'not_authorized':'No campaign/test rerun, model/environment construction or qualification opening.'})
    io.write('remaining-gap-register.json',{'unresolved_file_roles':122,'groups':gaps,
        'scope':'These are specific retained provenance groups. No invented global-workspace nonuse requirement is imposed.'})
    pins={}
    input_versions=collections.defaultdict(list)
    for name in ('discovery-input-pins.json','constructor-source-pins.json','closure-input-pins.json','control-copy-pins.json'):
        for row in load(name):
            path=row['path']
            if path.startswith(str(HERE.relative_to(ROOT))+'/'):continue
            version={'sha256':row['sha256'],'bytes':row['bytes'],'recorded_in':name}
            if version not in input_versions[path]:input_versions[path].append(version)
            pins[path]={'path':path,'sha256':row['sha256'],'bytes':row['bytes']}
    for row in load('early-source-archive-recovery.json'):
        path=ROOT/row['archive']
        pins[row['archive']]={'path':row['archive'],'sha256':row['archive_sha256'],'bytes':path.stat().st_size}
    changed_versions={path:versions for path,versions in input_versions.items() if len({v['sha256'] for v in versions})>1}
    io.write('input-version-changes.json',{'paths':changed_versions,
        'meaning':'Externally mutable inputs observed at different bytes during this audit. Preserve both hashes; no audit writes to these paths. Frozen evidence pin mismatches remain blockers.'})
    # Reports already read during the initial evidence review are pinned here as
    # context; root README and qualification outcome files are never added.
    extra=['learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/README.md',
           'learning/runs/v2/progressive1000-seed-cohort-prepare-sol-20261026-r1/prepare.py',
           'learning/runs/v2/expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/report.md',
           'learning/runs/v2/expanded-evaluation-seed-exposure-audit-luna-20261026-r1/report.md']
    for name in extra:
        p=ROOT/name;pins[name]={'path':name,'sha256':sha(p),'bytes':p.stat().st_size}
    # Do not reopen content from the recorded boundary incident. Hash checks on
    # qualification/mixed baseline paths are left explicitly unchecked.
    recheck={'checked':0,'unchanged':0,'mismatches':[],'excluded_from_recheck':[]}
    for name,row in sorted(pins.items()):
        if io.BLOCK.search(name) or re.search(r'(?i)(m0_expected|baseline|campaign-result|milestone0|results-summary)',name):
            recheck['excluded_from_recheck'].append(name);continue
        p=ROOT/name
        current=sha(p) if p.exists() else None
        recheck['checked']+=1
        if current==row['sha256']:recheck['unchanged']+=1
        else:recheck['mismatches'].append({'path':name,'pinned':row['sha256'],'current':current})
    io.write('input-pins.json',{'files':list(sorted(pins.values(),key=lambda x:x['path'])),
        'meaning':'Exact bytes read or hashed during provenance discovery. A pin is not execution evidence. Boundary incident and explicitly unopened paths are separate.'})
    io.write('input-recheck.json',recheck)
    counts=collections.Counter(r['status'] for r in paths)
    closure_map={
        'status':'PARTIAL_HISTORY_CLOSURE_BLOCKED; QUALIFICATION_CONTENT_BOUNDARY_BREACHED',
        'authority':'Implementation audit only. Parent alone approves freshness and reserves a cohort.',
        'known_journaled_campaigns':{'finite_bounds':19,'unmatched_derivations':0,'artifact':'campaign-closure.json'},
        'six_requested_directories':{'closed_bounded_cases':6,'unresolved_cases':0,'artifact':'six-directory-closure.json'},
        'R1_unresolved_paths':{'total':1096,'closed_file_roles':974,'unresolved_file_roles':122,
                               'unresolved_groups':7,'status_counts':dict(counts),'artifact':'r1-unresolved-path-closure.json'},
        'nested_journals':{'current_regular_paths':839,'empty':837,'exact_ancestor_copies':2,
                          'prior_count_included_four_aliases':843,'artifact':'nested-journal-proof.json'},
        'observed_unique_seed_values':{'R1':87430,'new_raw_native_or_outside_v2':149,'merged':87579,
                                       'original_training':70301,'artifact':'additional-observed-seeds.json'},
        'conservative_coverage':{'retained_R1_envelope':164385,'tight_known_attempt_values':collision['tight_known_attempt_seed_count'],
                                 'fixed_possible_lists':collision['finite_fixed_list_count'],'merged':collision['merged_conservative_seed_count'],
                                 'cohort_collisions':collision['merged_conservative_collisions'],'artifact':'merged-conservative-seeds.json'},
        '97593849':'Retained envelope-only overlap. Master4200000000 slot44 construction starts at episode262; historical tuple episode48 is unused prefix. No consumption assertion or filter.',
        'D3':'Registered M3 D3 no-attempt supported by original/current lifecycle status, closeout receipt and absent matching run/launch paths. Not a global no-use claim.',
        'remaining_specific_actions':'remaining-gap-register.json',
        'future_stream':'Existing 98,304-draw bounded sample independently reproduced against merged history: only the retained 97593849 intersection, zero cohort hits. No unbounded enumeration. Canonical six-range native exclusions must apply before every construction/reset; matched streams do not establish equal episode counts.',
        'checkpoint_metadata_audit':{'used':False,'loads':0,'reason':'Existing terminal receipts, complete boundary metadata and original source supplied known-run bounds. Remaining gaps concern historical test constructors and seed-only qualification provenance, not missing checkpoint counters.'},
        'qualification_boundary':'boundary-incident.json; cannot claim no B/E outcome content was opened',
        'claim_limit':'No global-workspace freshness/nonuse claim. Metadata-role closure is not proof of every execution referenced by that file.'}
    io.write('coverage-closure-map.json',closure_map)
    io.write('updated-proposal-status.json',{'status':'BLOCKED_SPECIFIC_PROVENANCE_GAPS_AND_BOUNDARY_REVIEW',
        'study_id':'progressive1000-confirmed324-20261026-r1','replicas':[1,2,3],
        'vectors_sha256':'698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf',
        'cohort_sha256':'dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45',
        'cohort_inclusive':['0xD3000000','0xD30003FF'],'cohort_size':1024,'proposal_retained':True,
        'collision_found_in_covered_finite_sets':False,'approved_freshness':False,'reserved':False,'exclusions_installed':False,
        'parent_gates':['Resolve seven named retained provenance groups, or explicitly scope a parent decision to the proven history. Do not relabel this partial audit global nonuse.',
                        'Review recorded qualification-content boundary breach; do not treat this implementation audit as a blinded qualification audit.',
                        'Parent alone approves freshness/reservation and reviewed preconstruction/reset six-range exclusions in both arms.'],
        'future_training_history_disjointness':'No additional requirement inferred beyond protocol; 97593849 is not a cohort collision.',
        'matching_streams':'Same registered master/offsets identify streams; realized reset counts may differ across arms.'})
    receipt={'schema':'progressive1000_seed_history_closure_v2','owned_output':str(HERE.relative_to(ROOT)),
        'status':'partial_closure_delivered_with_recorded_boundary_breach',
        'controls':{'inherited_stdlib':17,'independent_stdlib':12,'passed':True,
                    'logs':['tests-r1-controls-complete.log','tests-independent-initial.log'],
                    'retained_initial_control_setup_failure':'tests-r1-controls.log; observed-seeds.json copy initially missing, then supplied; no predecessor control/preparation rerun'},
        'checkpoint_loads':0,'project_runtime_imports':0,'actual_model_env_training_eval_study_runs':0,
        'reservations':0,'subdelegation':0,'commits':0,'pushes':0,
        'cohort_hits':0,'merged_possible_seed_values':collision['merged_conservative_seed_count'],
        'remaining_unresolved_file_roles':122,'remaining_named_groups':7,
        'input_recheck':recheck,'externally_changed_input_versions':changed_versions,'qualification_content_isolation_passed':False,
        'retained_finalization_setup_failure':'First finalization rejected two observed versions of externally mutable learning/runs/v2-orchestration/state.json. Both hashes retained in input-version-changes.json; no source or campaign rerun.',
        'scope':'Files were written only under this new R2 directory. Source reads and arithmetic do not grant freshness or launch authority.'}
    io.write('receipt.json',receipt)
    (HERE/'README.md').write_text('''# Progressive1000 historical seed closure R2

Partial closure delivered; freshness remains blocked. Exact R1 vectors and cohort are unchanged. Parent alone approves freshness and reserves a cohort.

- Six requested journal-free directory cases now have finite coverage or preconstructor/copy proofs. Nineteen original campaigns have pinned masters, actual initial offsets, terminal/resume indices, failure disposition, source identity and conservative failed-reset endpoints. All original seed metadata replayed with zero derivation mismatches. [Campaigns](campaign-closure.json), [six cases](six-directory-closure.json), [source semantics](source-semantics.json).
- All 1,096 R1 unresolved paths have an evidence role: **974 file roles closed; 122 remain unresolved in seven named groups**. These are file counts, not independent campaigns. Remaining work concerns exact early native test constructors and an outcome-free gate-baseline seed receipt. [Every path](r1-unresolved-path-closure.json), [precise remaining actions](remaining-gap-register.json).
- Current nested journal inventory has **837 empty files and two exact ancestor copies**, verified by bytes. R1's 843 paths included four symlink aliases. Empty journal content does not prove its surrounding job never constructed an environment. [Hash proof](nested-journal-proof.json).
- Raw native controls and outside-v2 episode records add **149** observed seed values: **87,579 merged observed**, including the original **70,301 training values**. Retaining R1's **164,385-value** zero-origin envelope and adding finite known attempt/reset bounds and fixed lists yields **189,743 conservative values**. **Zero proposed-cohort collisions** appear in these covered finite sets. [Collision check](cohort-collision-check.json), [merged set](merged-conservative-seeds.json), [new observations](additional-observed-seeds.json).
- `97593849` remains in the retained R1 envelope. Its historical tuple is master `4200000000`, slot44, episode48; actual construction for that slot starts at **episode262**. It is absent from observed history and the tighter known-attempt set. This is an unused-prefix arithmetic match, not consumption. No filtering or seed replacement occurred. [Reconciliation](97593849-reconciliation.json).
- Registered M3 D3 master `5562881586070242563` has an explicit original/current `not_started` lifecycle status, a closeout receipt, and no matching retained M3 D3 run/launch path. This closes that registered campaign's no-attempt question within retained evidence. Fixed-seed native difficulty-D3 baselines are distinct. [D3 evidence](d3-no-attempt.json).

**Boundary breach:** source searches inadvertently surfaced B baseline expected-result tables in loose `baseline_expected.rs` and archived `m0_expected.rs`. Those rows were excluded from seed-collision evidence. This audit cannot claim the requested qualification-content isolation was preserved. Parent review remains required. [Incident](boundary-incident.json).

The proposal remains `progressive1000-confirmed324-20261026-r1`, replicas1..3, accepted324 offsets, cohort `0xD3000000..0xD30003FF` (1024), and the exact canonical six-range future exclusion union. Vector file SHA-256: `698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf`. Cohort file SHA-256: `dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45`. [Updated status](updated-proposal-status.json).

The existing 98,304-draw future sample independently reproduces against merged history: only `97593849` intersects, with zero cohort hits. [Bounded recheck](future-merged-recheck.json). No full future stream was enumerated. Reviewed native exclusions must avoid the cohort before every construction/reset in both arms. Matching master/offset streams do not imply identical realized episode counts. No extra requirement that all future training seeds avoid all historical training seeds was imposed.

Input sealing found externally changed/removed `confirmed324-restore-probe-prepare-sol-20261026-r1/{prepare_files.py,probe.py,supervisor_cli.py}` and multiple orchestration-state versions. Known campaign and R1 proposal evidence pins remained stable. These external changes were recorded without editing or reverting predecessors. [Recheck](input-recheck.json), [state versions](input-version-changes.json).

Verification: **17 inherited controls and 12 independent controls passed**, using owned copies and independent stdlib derivation/coverage checks. Initial control-copy setup failure is retained. No checkpoint metadata loads were needed; no model, native environment, training, evaluation, study run, reservation, subdelegation, commit or push occurred. R1 preparation was never rerun. [Receipt](receipt.json), [input pins](input-pins.json), [input recheck](input-recheck.json), [coverage closure map](coverage-closure-map.json).

Reproduce arithmetic controls from workspace root (writes no predecessors):

```sh
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/test_controls.py
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/test_closure.py
```
''')
    manifest=[]
    for p in sorted(HERE.rglob('*')):
        if p.is_file() and p.name!='output-manifest.json' and '__pycache__' not in p.parts:
            manifest.append({'path':str(p.relative_to(HERE)),'bytes':p.stat().st_size,'sha256':sha(p)})
    io.write('output-manifest.json',manifest)
    print(json.dumps({'inputs':len(pins),'recheck_checked':recheck['checked'],'recheck_mismatches':len(recheck['mismatches']),
        'outputs':len(manifest),'status':receipt['status']}))

if __name__=='__main__':main()
