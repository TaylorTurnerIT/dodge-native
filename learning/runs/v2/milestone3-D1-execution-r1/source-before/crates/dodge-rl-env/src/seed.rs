use crate::{EnvError, SeedMode};

pub const SEED_EXCLUSION_VERSION: &str = "mandatory_b_plus_inclusive_union_rehash_v1";
pub const MANDATORY_SEED_RANGE: (u32, u32) = (0xB000_0000, 0xB000_03E7);

/// Sorted, disjoint effective union, including mandatory B. Reject complete
/// coverage before hashing: it would otherwise make rejection nonterminating.
pub fn normalize_seed_exclusions(additional: &[(u32, u32)]) -> Result<Vec<(u32, u32)>, EnvError> {
    let mut ranges = additional.to_vec();
    if ranges.iter().any(|(start, end)| start > end) {
        return Err(EnvError::Config("excluded seed range start exceeds end"));
    }
    ranges.push(MANDATORY_SEED_RANGE);
    ranges.sort_unstable();
    let mut union: Vec<(u32, u32)> = Vec::new();
    for (start, end) in ranges {
        if let Some(last) = union.last_mut()
            && u64::from(start) <= u64::from(last.1) + 1
        {
            last.1 = last.1.max(end);
        } else {
            union.push((start, end));
        }
    }
    if union == [(0, u32::MAX)] {
        return Err(EnvError::Config("excluded seed union covers all u32 seeds"));
    }
    Ok(union)
}

pub const SEED_STREAM_VERSION: &str = "dodge_slot_splitmix64_high32_reject_v1";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SeedMetadata {
    pub slot: usize,
    pub episode: u64,
    /// Rehash counter; zero is the first candidate. Also the rejection count.
    pub counter: u64,
    pub actual_seed: u32,
    pub evaluation: bool,
}

/// SplitMix64 finalizer, with explicit wrapping arithmetic (not its PRNG step).
const fn mix(mut z: u64) -> u64 {
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Exact v1 tuple hash:
/// `base = mix(run ^ 0x444f4447455f5632) ^ mix(slot + 0x9e3779b97f4a7c15)
///         ^ mix(episode + 0xd1b54a32d192ed03)`;
/// candidate = upper 32 bits of `mix(base ^ mix(counter + 0x94d049bb133111eb))`.
/// Reject the inclusive M0 evaluation interval and advance only this counter.
pub fn training_seed(run: u64, slot: usize, episode: u64) -> Result<SeedMetadata, EnvError> {
    training_seed_with_exclusions(run, slot, episode, &[])
}

/// Same tuple hash and counter as v1, with validated additional reservations.
pub fn training_seed_with_exclusions(
    run: u64,
    slot: usize,
    episode: u64,
    additional: &[(u32, u32)],
) -> Result<SeedMetadata, EnvError> {
    let ranges = normalize_seed_exclusions(additional)?;
    training_seed_normalized(run, slot, episode, &ranges)
}

fn training_seed_normalized(
    run: u64,
    slot: usize,
    episode: u64,
    ranges: &[(u32, u32)],
) -> Result<SeedMetadata, EnvError> {
    let slot64 = u64::try_from(slot).map_err(|_| EnvError::CounterExhausted)?;
    let base = mix(run ^ 0x444F_4447_455F_5632)
        ^ mix(slot64.wrapping_add(0x9E37_79B9_7F4A_7C15))
        ^ mix(episode.wrapping_add(0xD1B5_4A32_D192_ED03));
    let (counter, actual_seed) = reject_ranges(ranges, |counter| {
        let bytes = mix(base ^ mix(counter.wrapping_add(0x94D0_49BB_1331_11EB))).to_be_bytes();
        u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]])
    })?;
    Ok(SeedMetadata {
        slot,
        episode,
        counter,
        actual_seed,
        evaluation: false,
    })
}

#[cfg(test)]
fn reject_reserved(candidate: impl FnMut(u64) -> u32) -> Result<(u64, u32), EnvError> {
    reject_ranges(&[MANDATORY_SEED_RANGE], candidate)
}

fn reject_ranges(
    ranges: &[(u32, u32)],
    mut candidate: impl FnMut(u64) -> u32,
) -> Result<(u64, u32), EnvError> {
    let mut counter = 0;
    loop {
        let seed = candidate(counter);
        if !ranges
            .iter()
            .any(|&(start, end)| (start..=end).contains(&seed))
        {
            return Ok((counter, seed));
        }
        counter = counter.checked_add(1).ok_or(EnvError::CounterExhausted)?;
    }
}

pub(crate) fn seed_for(
    mode: &SeedMode,
    slot: usize,
    episode: u64,
    ranges: &[(u32, u32)],
) -> Result<SeedMetadata, EnvError> {
    match mode {
        SeedMode::Training { run_seed } => {
            training_seed_normalized(*run_seed, slot, episode, ranges)
        }
        SeedMode::Evaluation { seeds_by_slot } => {
            let seed = usize::try_from(episode)
                .ok()
                .and_then(|i| seeds_by_slot.get(slot)?.get(i))
                .copied()
                .ok_or(EnvError::SeedExhausted { slot, episode })?;
            Ok(SeedMetadata {
                slot,
                episode,
                counter: 0,
                actual_seed: seed,
                evaluation: true,
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejection_rehashes_reserved_interval_including_both_edges() -> Result<(), EnvError> {
        let candidates = [0xB000_0000, 0xB000_03E7, 42];
        assert_eq!(reject_reserved(|i| candidates[i as usize])?, (2, 42));
        Ok(())
    }
}

#[cfg(test)]
#[path = "seed_reservation_tests.rs"]
mod reservation_tests;
