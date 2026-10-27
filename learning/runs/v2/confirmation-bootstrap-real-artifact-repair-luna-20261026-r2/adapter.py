"""Inert paired confirmation statistics over externally pinned evaluator artifacts."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np

N=2048; SEEDS=tuple(range(0xD2000000,0xD2000800)); CAUSES=("normal_enemy","kamikaze_enemy","kamikaze_explosion","static_pattern_rect","moving_pattern_rect","unknown","unavailable")
INCUMBENT="b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369"
BOOT_SEED=4200261026; RESAMPLES=20000; CAP=18000; CHUNK=128
class ContractError(ValueError): pass
def sha(b): return hashlib.sha256(b).hexdigest()
def fail(ok,msg):
    if not ok: raise ContractError(msg)
def pinned(raw,pin,label):
    fail(type(raw) is bytes and type(pin) is str and sha(raw)==pin,f"{label} raw-file SHA-256 mismatch")
    try: return json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as e: raise ContractError(f"{label} invalid JSON") from e
def _int(x): return type(x) is int
def _hash(x): return type(x) is str and len(x)==64 and all(c in '0123456789abcdef' for c in x)
def _load_result(raw,pin,*,reg,update,checkpoint,backend,cohort_hash,label):
    obj=pinned(raw,pin,label)
    fail(obj.get('schema')=='expanded_D2_candidate_evaluation_v1' and obj.get('complete') is True,f'{label} incomplete evaluator result')
    fail(obj.get('backend')==backend,f'{label} backend mismatch')
    fail(_int(obj.get('candidate_update')) and obj.get('candidate_update')==update,f'{label} candidate_update mismatch')
    for k,v in [('checkpoint_sha256',checkpoint),('cohort_name','confirmation'),('cohort_sha256',cohort_hash),('episodes',N)]: fail(obj.get(k)==v,f'{label} {k} mismatch')
    rows=obj.get('rows'); fail(type(rows) is list and len(rows)==N,f'{label} row count mismatch')
    alive=[]; counts={c:0 for c in CAUSES}; caps=0
    for idx,(row,seed) in enumerate(zip(rows,SEEDS)):
        fail(type(row) is dict and _int(row.get('seed')) and row['seed']==seed,f'{label} rows missing, duplicate, or permuted')
        for key in ('episode_index','alive_frames','gameplay_frames','startup_frames','score_raw_fixed','score_delta_sum_raw_fixed'):
            fail(_int(row.get(key)) and row[key]>=0,f'{label} row {key} invalid')
        fail(row['episode_index']==idx and row['startup_frames']==13 and row['score_raw_fixed']==row['score_delta_sum_raw_fixed'],f'{label} row identity/accounting mismatch')
        a,g=row['alive_frames'],row['gameplay_frames']; t,tr=row.get('terminated'),row.get('truncated')
        fail(type(t) is bool and type(tr) is bool and t != tr and a<=g<=CAP,f'{label} terminal flags/frame range invalid')
        if t:
            fail(a+1==g,f'{label} fatal-frame conservation mismatch'); cause=row.get('death_cause')
            fail(cause in CAUSES,f'{label} native death cause invalid'); counts[cause]+=1
            if cause=='unavailable': fail(row.get('fatal_gameplay_frame') is None and row.get('death_observed_lethal_contacts') is None,f'{label} unavailable telemetry mismatch')
            else:
                contacts=row.get('death_observed_lethal_contacts')
                fail(row.get('fatal_gameplay_frame')==g and type(contacts) is dict and set(contacts)==set(CAUSES[:-1]) and all(_int(v) and v>=0 for v in contacts.values()) and (cause=='unknown' or contacts[cause]>=1),f'{label} native death telemetry mismatch')
        else:
            fail(a==g==CAP and row.get('death_cause') is None and row.get('fatal_gameplay_frame') is None and row.get('death_observed_lethal_contacts') is None,f'{label} truncation/cap accounting mismatch'); caps+=1
        score=row.get('score'); objective=row.get('objective_return')
        fail(type(score) in (int,float) and math.isfinite(score) and score==row['score_raw_fixed']/65536,f'{label} score identity mismatch')
        expect=row['score_raw_fixed']/65536+a/100-5*t
        fail(type(objective) in (int,float) and math.isfinite(objective) and math.isclose(objective,expect,rel_tol=0,abs_tol=1e-9),f'{label} objective identity mismatch')
        alive.append(a)
    reported=obj.get('death_causes')
    fail(_int(obj.get('caps')) and obj.get('caps')==caps and type(reported) is dict and set(reported)==set(CAUSES) and all(_int(v) and v>=0 for v in reported.values()) and reported==counts,f'{label} summary death/cap counts mismatch')
    return np.asarray(alive,dtype=np.float64),counts,caps
def analyze(*,registration_bytes,registration_sha256,selection_bytes,selection_sha256,audit_bytes,audit_sha256,winner_bytes,winner_sha256,winner_path,incumbent_bytes,incumbent_sha256,incumbent_path):
    reg=pinned(registration_bytes,registration_sha256,'registration')
    fail(reg.get('schema')=='expanded_D2_evaluation_registration_v1' and reg.get('mode')=='confirmation','registration schema/mode mismatch')
    fail(type(reg.get('run_id')) is str and reg['run_id'],'registration run_id missing')
    cohort=reg.get('cohorts',{}).get('confirmation',{}); mp=cohort.get('manifest_path'); mh=cohort.get('manifest_sha256')
    fail(cohort.get('count')==N and mh=='d2594d710820ee2942aff20a11ca4dd049f1d605f6cce2950ce0018a71994d67' and type(mp) is str and Path(mp).is_absolute(),'confirmation manifest registration mismatch')
    # Caller supplies manifest bytes by embedding them in registration integration; path/hash remain pinned metadata.
    seeds=list(SEEDS); cohort_hash=mh
    selref=reg.get('selection_record'); fail(type(selref) is dict and set(selref)=={'path','sha256','winner_update','winner_checkpoint_sha256','incumbent_checkpoint_sha256'},'selection registration interface mismatch')
    sel=pinned(selection_bytes,selection_sha256,'selection')
    fail(selref.get('sha256')==selection_sha256 and type(selref.get('path')) is str and Path(selref['path']).is_absolute(),'selection bytes differ from registration pin')
    fail(sel.get('schema')=='expanded_D2_selection_record_v3' and sel.get('ranking_metric')=='mean_alive_frames_all_1024_including_caps' and sel.get('confirmation_status')=='eligible_for_parent_confirmation_gate' and type(sel.get('ranking_results')) is list and len(sel['ranking_results'])==6,'selection record schema/provenance/status mismatch')
    update=sel.get('winner_update'); fail(_int(update) and update in (180,204,276,300,324) and update!=348,'selection winner is not an eligible frozen candidate')
    candidates=reg.get('candidates',{}); wh=candidates.get(str(update),{}).get('checkpoint_sha256'); ih=candidates.get('348',{}).get('checkpoint_sha256')
    fail(wh==sel.get('winner_checkpoint_sha256')==selref.get('winner_checkpoint_sha256') and ih==sel.get('incumbent_checkpoint_sha256')==selref.get('incumbent_checkpoint_sha256')==INCUMBENT,'selection checkpoint pins differ from registration/accepted 348')
    fail(selref.get('winner_update')==update,'selection winner update differs from registration')
    backend=reg.get('runtime',{}).get('backend'); fail(backend in ('cpu','mps'),'registration runtime backend missing')
    w,wdeath,wcap=_load_result(winner_bytes,winner_sha256,reg=reg,update=update,checkpoint=wh,backend=backend,cohort_hash=cohort_hash,label='winner')
    i,ideath,icap=_load_result(incumbent_bytes,incumbent_sha256,reg=reg,update=348,checkpoint=ih,backend=backend,cohort_hash=cohort_hash,label='incumbent')
    fail(type(winner_path) is str and Path(winner_path).is_absolute() and type(incumbent_path) is str and Path(incumbent_path).is_absolute(),'result artifact paths must be absolute')
    audit=pinned(audit_bytes,audit_sha256,'terminal audit')
    fail(audit.get('schema')=='parent_expanded_confirmation_terminal_audit_v1' and audit.get('status')=='accepted_confirmation_evidence_only_no_promotion','terminal audit status/schema invalid')
    fail(audit.get('run_id')==reg['run_id'] and audit.get('registration_sha256')==registration_sha256,'terminal audit run/registration mismatch')
    fail(_int(audit.get('raw_supervisor_exit')) and audit.get('raw_supervisor_exit')==0 and _int(audit.get('raw_worker_exit')) and audit.get('raw_worker_exit')==0 and audit.get('process_group_absent') is True and audit.get('promotion') is False,'terminal audit exits/process/promotion invalid')
    artifacts=audit.get('output_artifacts'); fail(type(artifacts) is list,'terminal audit artifacts missing')
    expected={winner_path:winner_sha256,incumbent_path:incumbent_sha256}
    got={x.get('path'):x.get('sha256') for x in artifacts if type(x) is dict}
    fail(len(got)==len(artifacts) and got==expected,'terminal audit does not bind exact result paths and hashes')
    d=w-i; rng=np.random.Generator(np.random.PCG64(BOOT_SEED)); boot=np.empty(RESAMPLES)
    for start in range(0,RESAMPLES,CHUNK):
        stop=min(start+CHUNK,RESAMPLES); ix=rng.integers(0,N,size=(stop-start,N),dtype=np.int64); boot[start:stop]=d[ix].mean(axis=1)
    def summary(v,death,cap):
        s=np.sort(v); return {'worst':float(s[0]),'q1_bottom_quarter_mean':float(s[:512].mean()),'mean':float(v.mean()),'q4_top_quarter_mean':float(s[-512:].mean()),'best':float(s[-1]),'death_causes':death,'caps':cap}
    lb=float(np.quantile(boot,.05,method='linear'))
    return {'schema':'inert_confirmation_statistics_v2','run_id':reg['run_id'],'registration_sha256':registration_sha256,'winner_update':update,'winner_checkpoint_sha256':wh,'incumbent_update':348,'incumbent_checkpoint_sha256':ih,'finite_cohort_mean_difference_winner_minus_348':float(d.mean()),'paired_bootstrap_lower_bound_5pct':lb,'eligibility':'eligible' if lb>0 else 'inconclusive','winner':summary(w,wdeath,wcap),'incumbent_348':summary(i,ideath,icap),'bootstrap':{'generator':'numpy.random.PCG64','seed':BOOT_SEED,'resamples':RESAMPLES,'quantile_method':'linear','chunk_resamples':CHUNK,'same_seed_indices_for_both_models':True},'limits':['provisional contract pending parent integration and review','statistics only; no promotion, ledger write, or retry authority']}
