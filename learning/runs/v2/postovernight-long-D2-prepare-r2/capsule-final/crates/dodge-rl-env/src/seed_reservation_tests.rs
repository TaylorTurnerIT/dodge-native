use super::*;

#[test]
fn forced_b_d_e_edges_rehash_the_same_counter() -> Result<(), EnvError> {
    let ranges =
        normalize_seed_exclusions(&[(0xD000_0000, 0xD000_007F), (0xE000_0000, 0xE000_03E7)])?;
    let candidates = [
        0xB000_0000,
        0xB000_03E7,
        0xD000_0000,
        0xD000_007F,
        0xE000_0000,
        0xE000_03E7,
        0xE000_03E8,
    ];
    assert_eq!(
        reject_ranges(&ranges, |i| candidates[i as usize])?,
        (6, 0xE000_03E8)
    );
    Ok(())
}

#[test]
fn normalize_merges_overlap_adjacency_and_preserves_u32_edges() -> Result<(), EnvError> {
    assert_eq!(
        normalize_seed_exclusions(&[(9, 12), (0, 3), (4, 8), (u32::MAX, u32::MAX)])?,
        vec![(0, 12), MANDATORY_SEED_RANGE, (u32::MAX, u32::MAX)]
    );
    assert!(normalize_seed_exclusions(&[(8, 7)]).is_err());
    assert!(normalize_seed_exclusions(&[(0, u32::MAX)]).is_err());
    assert!(normalize_seed_exclusions(&[(0, 100), (101, u32::MAX)]).is_err());
    Ok(())
}
