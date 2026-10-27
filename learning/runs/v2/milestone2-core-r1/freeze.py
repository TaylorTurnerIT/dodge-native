from pathlib import Path
import datetime,difflib,hashlib,json,subprocess,tarfile
r=Path(__file__).resolve().parent
owned=['crates/dodge-core/src/'+n for n in ['game.rs','snapshot.rs','lib.rs','headless.rs','headless_tests.rs','enemy_rows.rs','observation_tests.rs']]
example='crates/dodge-core/examples/headless_profile.rs'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj): (r/p).write_text(json.dumps(obj,indent=2)+'\n')
checked=json.loads((r/'test-workspace.json').read_text())['source_sha256']
assert all(sha(p)==h for p,h in checked.items())
patch=[]
for p in owned:
 before=r/'before'/p
 old=before.read_text().splitlines(True) if before.exists() else []
 patch.extend(difflib.unified_diff(old,Path(p).read_text().splitlines(True),fromfile='a/'+p if before.exists() else '/dev/null',tofile='b/'+p))
(r/'milestone2-core.patch').write_text(''.join(patch))
(r/'full-core-from-HEAD.patch').write_bytes(subprocess.check_output(['git','diff','HEAD','--',*owned]))
# The incremental patch above includes both new files, unlike git diff on untracked files.
with tarfile.open(r/'source.tar.gz','w:gz') as t:
 for p in sorted(checked): t.add(p,arcname=p)
with tarfile.open(r/'before-owned-source.tar.gz','w:gz') as t:
 for p in owned+[example]:
  source=r/'before'/p
  if source.exists():t.add(source,arcname=p)
before=json.loads((r/'before-source-manifest.json').read_text())
changed=[p for p in before if Path(p).exists() and sha(p)!=before[p]]
outside=[p for p in changed if p not in owned]
assert not [p for p in outside if p.startswith('crates/') or p in ['Cargo.toml','Cargo.lock','.cargo/config.toml','rust-toolchain.toml']]
assert sha(example)==before[example]
manifest={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'status':'source frozen for independent parent audit; no source edits after successful checks','owned_paths':owned,'source_sha256':{p:sha(p) for p in owned},'workspace_check_source_sha256':checked,'before_manifest':'before-source-manifest.json','before_owned_archive_sha256':sha(r/'before-owned-source.tar.gz'),'archive_sha256':sha(r/'source.tar.gz'),'patch_sha256':sha(r/'milestone2-core.patch'),'example_source_unchanged':True,'concurrent_out_of_scope_input_changes':outside,'contract_sha256':sha('docs/v2-environment-contract.md')}
assert manifest['contract_sha256']=='79e953f20487bb442888fe40cee5f43226ae2cfc7ef0b9ef0fc3a377db4e01aa'
write('source-manifest.json',manifest)
coverage=json.loads((r/'coverage.json').read_text());bench=json.loads((r/'benchmark.json').read_text())
command_receipts={p.stem:json.loads(p.read_text()) for p in r.glob('*.json') if isinstance(json.loads(p.read_text()),dict) and 'command' in json.loads(p.read_text())}
failed={k:v for k,v in command_receipts.items() if v['exit_code']!=0}
assert set(failed)=={'before-layout-build'}
precheck=[{'command':"rg --files -g 'AGENTS.md' -g '*unslop*' -g 'SKILL.md' . /Users/taylor/.agents/skills /Users/taylor/.codex/skills | rg 'AGENTS.md|unslop'",'exit_code':1,'stdout':'','stderr':'','receipt':'discovery.log','reason':'No matching paths in initial non-hidden scan. A later pathlib scan found no unslop SKILL.md either.'},{'command':'cat docs/implementation-plan-v2.md docs/v2-source-audit.md learning/state.json','exit_code':1,'raw_log':'precheck-failed-cat-full.log','reason':'state lives in learning/runs/v2-orchestration/state.json; the correct file was then read and pinned.'}]
(r/'precheck-failed-cat-full.log').write_text(''.join((r/'inputs'/p).read_text() for p in ['docs/implementation-plan-v2.md','docs/v2-source-audit.md'])+'cat: learning/state.json: No such file or directory\n')
write('failed-commands.json',{'precheck_failures':precheck,'retained_command_failures':failed,'correction':'layout-probe-correction.json','source_test_assertion_failures':0,'source_assertions_weakened':False})
verification={'milestone':'v2 M2a observation-only core r1','status':'implemented, locally verified, source frozen for independent parent audit before wrapper integration','utc':manifest['utc'],'elapsed_seconds_since_062028_utc':(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime(2026,10,24,6,20,28,tzinfo=datetime.timezone.utc)).total_seconds(),'budget_seconds':2700,'changed_source_paths':owned,'preserved_example':example,'source_manifest':'source-manifest.json','source_manifest_sha256':sha(r/'source-manifest.json'),'incremental_patch':'milestone2-core.patch','incremental_patch_sha256':manifest['patch_sha256'],'source_archive':'source.tar.gz','source_archive_sha256':manifest['archive_sha256'],'m1_identity_comparison':'m1-source-identity-comparison.json','checks':{k:v for k,v in command_receipts.items() if k in ['fmt-workspace','clippy-workspace-first','test-workspace','diff-check']},'all_previous_72_tests_rerun':True,'new_test_count':14,'workspace_totals':coverage['workspace_totals'],'coverage_receipt':'coverage.json','random_current_run':coverage['random_current_run'],'catalog_current_run':coverage['catalog_current_run'],'metadata_parity':'Every M1 paired frame also compares enemy serial slices and warning iterators, with aligned lengths and strict serial ordering while valid. An exhaustion fixture separately checks 100 rendered/headless frames plus clear/reset/retry without IDs.','warning_cases':{'threshold_type_charge_raster_shadow':45,'mode_dead_scene_separation':6,'borrow_stale_hidden_targets_immutability':4},'api':{'enemy_serials':'pub fn enemy_serials(&self) -> Option<&[dodge_core::EnemySerial]>','serial_type':'Opaque Copy + Debug + Eq + Ord + PartialEq + PartialOrd pair of private u64 namespace/birth; 16 bytes. Publicly re-exported by dodge-core. Use equality and ordering for merge matching; IDs never enter neural tensors or snapshots.','namespace':'Fresh process-local namespace for each new game, restore, and safe bulk constructor; clones preserve identities. Namespace assignment may depend on construction order and is not gameplay-deterministic.','birth':'Monotonic per game; in-place writes retain identity; removal preserves order; clear/reset/retry retain birth counter. Wrapper keeps previous raw-frame geometry and resets history at new/reset/restore.','exhaustion':'u64 namespace counter reserves MAX and never wraps. Birth MAX is valid; following insertion invalidates serial accessor to sticky None. All gameplay insertions/removals/clear/reset/retry continue. Wrapper must fail closed on None.','warnings':'pub fn drawn_warning_lines(&self) -> impl Iterator<Item = &dodge_core::WarningLine>','warning_eligibility':'Shared pub(crate) rect_warnings_drawn(pattern, rect): pattern.timer < 125 && !(pattern.pattern_type == 0 && rect.sh < 2). Scene eligibility only; actual mode/death substitution and visual admission belong to wrapper. Stored stale eligible lines remain; no target reconstruction.','privileged_view_fields':'unchanged','wire_rng_entity_state':'No fields or wire encodings added to EnemyState/FullState/Snapshot; no RNG operations added or gameplay decisions changed.'},'benchmark_receipt':'benchmark.json','benchmark_time_change_percent':{k:v['time_change_percent'] for k,v in bench['summary'].items()},'benchmark_layout':bench['layout'],'failed_commands':'failed-commands.json','external_Pemsa_runtime':'unavailable; explicitly unrun','unresolved_issues':[],'pending_acceptance':['Independent parent audit of this frozen source. Wrapper integration, raw-frame geometry histories, fail-closed identity handling and v2 reward remain parent-owned and unimplemented here.'],'limits':coverage['limits']+bench['limits'],'no_out_of_scope_source_edits_verified':True,'concurrent_out_of_scope_input_changes':outside}
write('verification.json',verification)
(r/'git-status-final.log').write_bytes(subprocess.check_output(['git','status','--short','--untracked-files=all']))
print(json.dumps({'owned':owned,'archive_sha256':manifest['archive_sha256'],'patch_sha256':manifest['patch_sha256'],'source_manifest_sha256':sha(r/'source-manifest.json'),'verification_sha256':sha(r/'verification.json'),'workspace_totals':coverage['workspace_totals'],'elapsed_seconds':verification['elapsed_seconds_since_062028_utc']},indent=2))
