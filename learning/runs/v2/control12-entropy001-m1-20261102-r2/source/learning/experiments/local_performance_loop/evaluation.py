"""Accepted068 clean sampledK1 semantics on fixed development seeds."""
import gc
import hashlib
import common as c
from policy import summarize


def policy_seed(seed):
    return int.from_bytes(hashlib.sha256(f'dodge068/paired-policy-v1/{seed}/clean'.encode()).digest()[:8],'big')


def evaluate(model,seeds,reg,out,guard,torch,np,native,checkpoint,fingerprint):
    saved_rng=checkpoint.capture_rng('mps');rng_hash=fingerprint(saved_rng)
    model_hash=fingerprint(model.state_dict());was_training=model.training;model.eval()
    rows=[];frames=0;journal=c.Journal(out/'episodes.jsonl')
    try:
        keys=('global_feats','entity_feats','entity_types','entity_mask')
        for offset in range(0,len(seeds),64):
            environments={};observations={};episode={}
            for seed in seeds[offset:offset+64]:
                guard()
                env=native.VecDodgeEnv(batch_size=1,action_repeat=1,difficulty=2,patterns_enabled=True,powerups_enabled=True,
                    raw_frame_cap=18000,num_threads=1,chunk_size=1,render_pixels=False,auxiliary_targets=False,
                    seeds_by_slot=[[seed]],excluded_seed_ranges=[tuple(x) for x in reg['exclusions'] if x!=[3657433088,3657435135]])
                info=env.episode_info()[0];c.need(info['seed']['actual_seed']==seed and info['startup_frames']==13,'Evaluation seed/startup differs')
                environments[seed]=env;observations[seed]=env.observations()
                episode[seed]=dict(generator=torch.Generator(device='cpu').manual_seed(policy_seed(seed)),decisions=0)
            del env
            while environments:
                guard();active=sorted(environments)
                arrays=[torch.from_numpy(np.concatenate([observations[s][k] for s in active],axis=0)) for k in keys]
                if not getattr(model,'cpu_geometry_inputs',False):arrays=[x.to('mps') for x in arrays]
                with torch.no_grad():output=model(*arrays);probabilities=output.logits.softmax(-1).cpu()
                c.need(output.logits.device.type=='mps' and bool(torch.isfinite(probabilities).all()),'Evaluation device/finiteness')
                for i,seed in enumerate(active):
                    row=episode[seed];request=int(torch.multinomial(probabilities[i],1,generator=row['generator']).item())
                    result=environments[seed].step(np.array([request],dtype=np.int64));info=result['info'][0]
                    c.need(info['seed']['actual_seed']==seed and int(result['elapsed_raw_frames'][0])==1,'Evaluation native K1/seed drift')
                    row['decisions']+=1;frames+=1;term,trunc=bool(result['terminated'][0]),bool(result['truncated'][0])
                    if term or trunc:
                        n=row['decisions'];c.need(term!=trunc and info['gameplay_frames']==n and info['alive_frames']==n-int(term) and (not trunc or n==18000),'Evaluation terminal identity')
                        record=dict(seed=seed,condition='clean',alive_frames=int(info['alive_frames']),gameplay_frames=n,
                            terminated=term,truncated=trunc,decisions=n,startup_frames=13,score_raw_fixed=int(info['score_raw_fixed']))
                        journal.emit(record);rows.append(record);del environments[seed],observations[seed]
                    else:observations[seed]=result['observations']
            journal.sync();del arrays,output,probabilities,result,observations,environments,episode
            gc.collect();torch.mps.empty_cache()
        journal.close();journal=None
        c.need(sorted(r['seed'] for r in rows)==seeds,'Evaluation coverage differs')
        c.need(fingerprint(model.state_dict())==model_hash,'Evaluation changed weights')
        result=dict(status='complete_development_play_check',metrics=summarize(rows),games=len(rows),actual_frames=frames,
            model_fingerprint=model_hash,episodes_sha256=c.sha(out/'episodes.jsonl'),training=False,promoted=False)
        c.save(out/'result.json',result);return result
    finally:
        if journal is not None:journal.close()
        model.train(was_training);checkpoint.restore_rng(saved_rng,'mps')
        c.need(fingerprint(checkpoint.capture_rng('mps'))==rng_hash,'Evaluation did not restore training RNG')
