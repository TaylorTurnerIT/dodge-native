//! Supplemental correctness check across populated episodes and partial resets.
//! No timing/throughput result is computed or claimed.
use dodge_rl_env::{EnvConfig, SeedMode, VecDodgeEnv, training_seed};
fn main() -> Result<(),Box<dyn std::error::Error>> {
    let config=EnvConfig {batch_size:9,raw_frame_cap:600,render_pixels:true,auxiliary_targets:true,
        seed_mode:SeedMode::Training{run_seed:0xFFFF_FFFF_1234_5678},..EnvConfig::default()};
    let mut a=VecDodgeEnv::new(EnvConfig{num_threads:1,chunk_size:1,..config.clone()})?;
    let mut b=VecDodgeEnv::new(EnvConfig{num_threads:4,chunk_size:3,..config})?;
    assert_eq!(a.observations()?,b.observations()?);
    let mut raw_frames=0_u64;let mut deaths=0;let mut caps=0;let mut max_enemies=0;let mut resets=0;
    for decision in 0..300 {
        let actions:Vec<_>=(0..9).map(|slot|(decision*7+slot*3)%9).collect();
        let left=a.step(&actions)?;let right=b.step(&actions)?;assert_eq!(left,right);
        raw_frames+=left.elapsed_raw_frames.iter().map(|v|u64::from(*v)).sum::<u64>();
        deaths+=left.terminated.iter().filter(|v|**v).count();caps+=left.truncated.iter().filter(|v|**v).count();
        max_enemies=max_enemies.max(left.observations.diagnostics.iter().map(|d|d.admitted_enemies).max().unwrap());
        let ended:Vec<_>=left.info.iter().enumerate().filter(|(_,i)|i.terminated || i.truncated).map(|(slot,_)|slot).collect();
        if !ended.is_empty() {assert_eq!(a.reset_done(&ended)?,b.reset_done(&ended)?);resets+=ended.len();}
    }
    assert!(max_enemies>0 && deaths>0 && resets>0);
    println!("TRAJECTORY {{\"batch_size\":9,\"decisions\":300,\"raw_frames_per_batch\":{raw_frames},\"thread_chunk_pairs\":[[1,1],[4,3]],\"max_admitted_enemies\":{max_enemies},\"terminated\":{deaths},\"truncated\":{caps},\"explicit_slot_resets\":{resets},\"pixels\":true,\"auxiliary\":true}}");
    for run in [0_u64,1,0x1_0000_0001,u64::MAX] {
        for slot in [0,8] {for episode in [0,1] {
            let s=training_seed(run,slot,episode)?;
            println!("SEED_REFERENCE {{\"run\":{run},\"slot\":{slot},\"episode\":{episode},\"counter\":{},\"actual_seed\":{}}}",s.counter,s.actual_seed);
        }}
    }
    Ok(())
}
