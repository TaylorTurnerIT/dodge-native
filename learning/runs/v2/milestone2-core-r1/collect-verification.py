from pathlib import Path
import collections,datetime,hashlib,json,re
r=Path(__file__).resolve().parent
run=json.loads((r/'test-workspace.json').read_text());assert run['exit_code']==0;assert not run['source_changed_during_check']
log=(r/'test-workspace.log').read_text()
old=Path('learning/runs/v2/milestone1-r2/test-workspace.log').read_text()
def names(s): return collections.Counter(re.findall(r'^test ([\w:]+) \.\.\.',s,re.M))
previous=names(old);current=names(log);assert sum(previous.values())==72;assert not previous-current
results=[dict(zip(['passed','failed','ignored','measured','filtered_out'],map(int,m))) for m in re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out',log)]
totals={k:sum(x[k] for x in results) for k in results[0]};assert totals['passed']==86;assert all(totals[k]==0 for k in ['failed','ignored','measured','filtered_out'])
coverage=[];newcoverage=[]
for line in log.splitlines():
 if 'M1_COVERAGE_JSON ' in line: coverage.append(json.loads(line.split('M1_COVERAGE_JSON ',1)[1]))
 if 'M2_CORE_COVERAGE_JSON ' in line: newcoverage.append(json.loads(line.split('M2_CORE_COVERAGE_JSON ',1)[1]))
assert len(coverage)==15;assert len(newcoverage)==12
random=next(x for x in coverage if x['test']=='headless_equivalence_100_seeds_2000_raw_frames');assert random['raw_frames']==200000;assert random['case_counts']['random_seed']==100
catalog=next(x for x in coverage if x['catalog']);assert len(catalog['catalog'])==39;assert len({x['id'] for x in catalog['catalog']})==39;assert all(x['active_frames']>0 for x in catalog['catalog']);assert sum(x['active_frames'] for x in catalog['catalog'])==22843
fingerprints=next(x for x in coverage if x['test']=='legacy_capture_fingerprints');assert fingerprints['case_counts']['legacy_capture_fingerprint']==24
checks={p.stem:json.loads(p.read_text()) for p in r.glob('*.json') if p.stem in ['test-workspace','fmt-workspace','clippy-workspace-first']}
assert all(x['exit_code']==0 and not x['source_changed_during_check'] and x['source_sha256']==run['source_sha256'] for x in checks.values())
coverage_receipt={'m1_fixture_receipts_new_run':coverage,'m2_fixture_receipts_new_run':newcoverage,'new_tests':sorted((current-previous).elements()),'rerun_old_tests':sorted(previous.elements()),'workspace_totals':totals,'random_current_run':random,'catalog_current_run':{'entries':len(catalog['catalog']),'unique_ids':len({x['id'] for x in catalog['catalog']}),'active_frames':sum(x['active_frames'] for x in catalog['catalog']),'completed_count':sum(x['completed_count'] for x in catalog['catalog'])},'source_receipt':'test-workspace.json','limits':['Native Rust checks only; external Pemsa unavailable and explicitly unrun.','No geometry/wrapper/Python/student/training validation. Unregistered dodge-rl-env source is outside these workspace checks.','Random terminal residence is reported separately from alive gameplay; collision-disabled catalog fixtures are targeted coverage.']}
(r/'coverage.json').write_text(json.dumps(coverage_receipt,indent=2)+'\n')
print(json.dumps({'workspace_totals':totals,'new_tests':len(list((current-previous).elements())),'catalog':coverage_receipt['catalog_current_run'],'random_raw_frames':random['raw_frames'],'random_alive_game_frames':random['alive_game_frames'],'random_dead_frames':random['dead_frames']},indent=2))
