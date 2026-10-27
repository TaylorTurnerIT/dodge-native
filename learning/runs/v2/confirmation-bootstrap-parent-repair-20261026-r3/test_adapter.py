import copy, json, tempfile, unittest
from pathlib import Path
import numpy as np
import adapter

H=lambda c:c*64
def enc(x): return json.dumps(x,separators=(',',':'),sort_keys=True).encode()
def make_result(update,checkpoint,cohort,backend,values,registration_sha256):
    rows=[]
    for j,(seed,val) in enumerate(zip(adapter.SEEDS,values)):
        capped=val==adapter.CAP
        rows.append({'episode_index':j,'seed':seed,'score_raw_fixed':0,'score_delta_sum_raw_fixed':0,'alive_frames':val,'gameplay_frames':adapter.CAP if capped else val+1,'startup_frames':13,'terminated':not capped,'truncated':capped,'death_cause':None if capped else 'unavailable','fatal_gameplay_frame':None,'death_observed_lethal_contacts':None,'score':0,'objective_return':val/100-5*(not capped)})
    deaths={c:0 for c in adapter.CAUSES}; deaths['unavailable']=sum(not(r['truncated']) for r in rows)
    return {'registration_sha256':registration_sha256,'schema':'expanded_D2_candidate_evaluation_v1','complete':True,'candidate_update':update,'checkpoint_sha256':checkpoint,'cohort_name':'confirmation','cohort_sha256':cohort,'episodes':adapter.N,'caps':sum(r['truncated'] for r in rows),'death_causes':deaths,'backend':backend,'rows':rows}
def fixture(diff=1):
    cohort='d2594d710820ee2942aff20a11ca4dd049f1d605f6cce2950ce0018a71994d67'; winner=H('a'); incumbent=adapter.INCUMBENT
    with tempfile.TemporaryDirectory() as td:
        p=Path(td); selpath=p/'selection.json'; regpath=p/'reg.json'; wp=p/'winner.json'; ip=p/'incumbent.json'
        sel={'schema':'expanded_D2_selection_record_v3','winner_update':324,'winner_checkpoint_sha256':winner,'incumbent_checkpoint_sha256':incumbent,'ranking_metric':'mean_alive_frames_all_1024_including_caps','confirmation_status':'eligible_for_parent_confirmation_gate','ranking_results':[{'candidate_update':u,'path':f'/toy/ranking-{u}.json','sha256':H('b')} for u in (180,204,276,300,324,348)]}
        sb=enc(sel); selpath.write_bytes(sb)
        reg={'schema':'expanded_D2_evaluation_registration_v1','mode':'confirmation','run_id':'toy-run','runtime':{'backend':'cpu'},'cohorts':{'confirmation':{'manifest_path':'/toy/manifest.json','manifest_sha256':cohort,'count':adapter.N}},'selection_record':{'path':str(selpath),'sha256':adapter.sha(sb),'winner_update':324,'winner_checkpoint_sha256':winner,'incumbent_checkpoint_sha256':incumbent},'candidates':{'324':{'checkpoint_sha256':winner},'348':{'checkpoint_sha256':incumbent}}}
        rb=enc(reg); regpath.write_bytes(rb)
        wr=make_result(324,winner,cohort,'cpu',np.full(adapter.N,100+diff,dtype=int).tolist(),adapter.sha(rb)); ir=make_result(348,incumbent,cohort,'cpu',np.full(adapter.N,100,dtype=int).tolist(),adapter.sha(rb))
        wb,ib=enc(wr),enc(ir); wp.write_bytes(wb); ip.write_bytes(ib)
        audit={'schema':'parent_expanded_confirmation_terminal_audit_v1','status':'accepted_confirmation_evidence_only_no_promotion','run_id':'toy-run','registration_sha256':adapter.sha(rb),'raw_supervisor_exit':0,'raw_worker_exit':0,'process_group_absent':True,'promotion':False,'output_artifacts':[{'path':str(wp),'sha256':adapter.sha(wb)},{'path':str(ip),'sha256':adapter.sha(ib)}]}
        ab=enc(audit)
        return dict(registration_bytes=rb,registration_sha256=adapter.sha(rb),selection_bytes=sb,selection_sha256=adapter.sha(sb),audit_bytes=ab,audit_sha256=adapter.sha(ab),winner_bytes=wb,winner_sha256=adapter.sha(wb),winner_path=str(wp),incumbent_bytes=ib,incumbent_sha256=adapter.sha(ib),incumbent_path=str(ip))
class AdapterTests(unittest.TestCase):
    def runit(self,d=1): return adapter.analyze(**fixture(d))
    def test_constant_and_deterministic(self):
        self.assertEqual(self.runit(2)['eligibility'],'eligible'); self.assertEqual(self.runit(-1)['eligibility'],'inconclusive'); self.assertEqual(self.runit(0)['eligibility'],'inconclusive'); a=self.runit(1); b=self.runit(1); self.assertEqual(a['paired_bootstrap_lower_bound_5pct'],b['paired_bootstrap_lower_bound_5pct']); self.assertEqual(a['finite_cohort_mean_difference_winner_minus_348'],b['finite_cohort_mean_difference_winner_minus_348'])
    def test_real_shape_and_paired_cancellation(self):
        f=fixture(); cohort='d2594d710820ee2942aff20a11ca4dd049f1d605f6cce2950ce0018a71994d67'; w=make_result(324,H('a'),cohort,'cpu',(np.tile([0,100],1024)+np.tile([2,4],1024)).tolist(),f['registration_sha256']); i=make_result(348,adapter.INCUMBENT,cohort,'cpu',np.tile([0,100],1024).tolist(),f['registration_sha256']); f['winner_bytes']=enc(w); f['winner_sha256']=adapter.sha(f['winner_bytes']); f['incumbent_bytes']=enc(i); f['incumbent_sha256']=adapter.sha(f['incumbent_bytes']); a=json.loads(f['audit_bytes']); a['output_artifacts']=[{'path':f['winner_path'],'sha256':f['winner_sha256']},{'path':f['incumbent_path'],'sha256':f['incumbent_sha256']}]; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes']); out=adapter.analyze(**f); self.assertEqual(out['finite_cohort_mean_difference_winner_minus_348'],3); self.assertGreater(out['paired_bootstrap_lower_bound_5pct'],2.9)
    def test_pins_semantics_and_audit_identity(self):
        f=fixture(); f['winner_bytes']+=b' '; self.assertRaisesRegex(adapter.ContractError,'raw-file SHA',lambda:adapter.analyze(**f))
        for change in ('backend','cohort','winner','float','string','bool','death-key','row-order','failed-exit','foreign-audit'):
            f=fixture(); w=json.loads(f['winner_bytes'])
            if change=='backend': w['backend']='mps'
            elif change=='cohort': w['cohort_sha256']=H('d')
            elif change=='winner': w['candidate_update']=300
            elif change=='float': w['rows'][0]['alive_frames']=100.0
            elif change=='string': w['rows'][0]['alive_frames']='100'
            elif change=='bool': w['rows'][0]['seed']=True
            elif change=='death-key': w['death_causes']['invented']=0
            elif change=='row-order': w['rows'][0],w['rows'][1]=w['rows'][1],w['rows'][0]
            if change not in ('failed-exit','foreign-audit'):
                f['winner_bytes']=enc(w); f['winner_sha256']=adapter.sha(f['winner_bytes']); a=json.loads(f['audit_bytes']); a['output_artifacts'][0]['sha256']=f['winner_sha256']; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes'])
            else:
                a=json.loads(f['audit_bytes']); a['raw_worker_exit']=7 if change=='failed-exit' else 0; a['run_id']='foreign' if change=='foreign-audit' else 'toy-run'; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes'])
            with self.subTest(change=change): self.assertRaises(adapter.ContractError,lambda:adapter.analyze(**f))
    def test_selection_semantics_and_repin(self):
        for field,value in [('winner_update',348),('winner_checkpoint_sha256',adapter.INCUMBENT)]:
            f=fixture(); sel=json.loads(f['selection_bytes']); sel[field]=value; f['selection_bytes']=enc(sel); f['selection_sha256']=adapter.sha(f['selection_bytes']); reg=json.loads(f['registration_bytes']); reg['selection_record']['sha256']=f['selection_sha256']; reg['selection_record'][field]=value; f['registration_bytes']=enc(reg); f['registration_sha256']=adapter.sha(f['registration_bytes']); a=json.loads(f['audit_bytes']); a['registration_sha256']=f['registration_sha256']; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes']); self.assertRaises(adapter.ContractError,lambda:adapter.analyze(**f))
    def test_missing_and_duplicate_seed_rows_and_result_summary(self):
        for mutate in ('missing','duplicate','cause-count','cap-count'):
            f=fixture(); w=json.loads(f['winner_bytes'])
            if mutate=='missing': w['rows'].pop()
            elif mutate=='duplicate': w['rows'][1]['seed']=w['rows'][0]['seed']
            elif mutate=='cause-count': w['death_causes']['unavailable']-=1
            else: w['caps']=True
            f['winner_bytes']=enc(w); f['winner_sha256']=adapter.sha(f['winner_bytes']); a=json.loads(f['audit_bytes']); a['output_artifacts'][0]['sha256']=f['winner_sha256']; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes']); self.assertRaises(adapter.ContractError,lambda:adapter.analyze(**f))
    def test_all_capped_zero_native_deaths(self):
        cohort='d2594d710820ee2942aff20a11ca4dd049f1d605f6cce2950ce0018a71994d67'; f=fixture(0); w=make_result(324,H('a'),cohort,'cpu',[adapter.CAP]*adapter.N,f['registration_sha256']); f['winner_bytes']=enc(w); f['winner_sha256']=adapter.sha(f['winner_bytes']); a=json.loads(f['audit_bytes']); a['output_artifacts'][0]['sha256']=f['winner_sha256']; f['audit_bytes']=enc(a); f['audit_sha256']=adapter.sha(f['audit_bytes']); out=adapter.analyze(**f); self.assertEqual(out['winner']['death_causes'],{c:0 for c in adapter.CAUSES}); self.assertEqual(out['winner']['caps'],adapter.N)
if __name__=='__main__': unittest.main()
