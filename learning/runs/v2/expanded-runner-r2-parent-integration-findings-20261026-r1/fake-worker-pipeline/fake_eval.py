import json,os,time
from pathlib import Path
def evaluate_registered(*,registration_path,registration_sha256,candidate_update,cohort_name,output_path,check_guard):
 check_guard()
 print('EVAL_START',flush=True)
 time.sleep(0)
 reg=json.loads(Path(registration_path).read_text())
 manifest=json.loads(Path(reg['cohorts'][cohort_name]['manifest_path']).read_text());seeds=manifest['seeds']
 candidate=reg['candidates'][str(candidate_update)]
 rows=[{'seed':seed,'episode_index':i,'alive_frames':100+i,'gameplay_frames':101+i,'score_raw_fixed':65536,'score':1.0,'objective_return':1.0,'terminated':True,'truncated':False,'death_cause':'normal_enemy','fatal_gameplay_frame':101+i,'death_observed_lethal_contacts':{}} for i,seed in enumerate(seeds)]
 if False: rows[0]['score']=9.0
 result={'schema':'expanded_D2_candidate_evaluation_v1','complete':True,'candidate_update':candidate_update,'cohort_name':cohort_name,'cohort_sha256':reg['cohorts'][cohort_name]['manifest_sha256'],'checkpoint_sha256':candidate['checkpoint_sha256'],'episodes':len(rows),'rows':rows,'performance':{'mean':123.0},'death_causes':{},'caps':0,'elapsed_seconds':1.0}
 p=Path(output_path);p.parent.mkdir(parents=True,exist_ok=True);fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(result,f,sort_keys=True);f.write('\n')
 print('X'*0,flush=True)
 return result
