use std::{
    ops::Deref,
    sync::atomic::{AtomicU64, Ordering},
};

use crate::EnemyState;

/// Observation-only identity for one enemy-family birth.
///
/// Ordering is birth order within one game namespace. New games and restores
/// receive fresh process-local namespaces; clones preserve identities. These
/// values are not reproducible gameplay data or neural features and never enter
/// snapshots. A wrapper must keep histories per game and clear them on restore.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct EnemySerial {
    namespace: u64,
    birth: u64,
}

impl EnemySerial {
    /// Birth ordinal within this game's namespace, for the observation-only trace.
    pub(crate) const fn birth(self) -> u64 {
        self.birth
    }
}

// Reserve the final counter value instead of wrapping or reusing a namespace.
static NEXT_NAMESPACE: AtomicU64 = AtomicU64::new(0);

fn allocate_namespace(counter: &AtomicU64) -> Option<u64> {
    counter
        .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |next| {
            next.checked_add(1)
        })
        .ok()
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct IdentityRows {
    namespace: u64,
    next_birth: Option<u64>,
    serials: Vec<EnemySerial>,
}

/// Owns row structure and its identity metadata together. Mutable access only
/// reaches existing rows, so replacing a row's fields preserves its identity.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct EnemyRows {
    rows: Vec<EnemyState>,
    identities: Option<IdentityRows>,
}

impl EnemyRows {
    pub(crate) fn new() -> Self {
        Self {
            rows: Vec::new(),
            identities: allocate_namespace(&NEXT_NAMESPACE).map(|namespace| IdentityRows {
                namespace,
                next_birth: Some(0),
                serials: Vec::new(),
            }),
        }
    }

    #[cfg(test)]
    pub(crate) fn last_birth_fixture() -> Self {
        let mut result = Self::new();
        if let Some(ids) = &mut result.identities {
            ids.next_birth = Some(u64::MAX);
        }
        result
    }

    pub(crate) fn from_rows(rows: Vec<EnemyState>) -> Self {
        let mut result = Self::new();
        for row in rows {
            result.push(row);
        }
        result
    }

    /// None is sticky after namespace or birth exhaustion, even across clears.
    /// The last representable birth is valid; the next insertion invalidates
    /// the entire identity view while still inserting the gameplay row.
    pub(crate) fn serials(&self) -> Option<&[EnemySerial]> {
        self.identities.as_ref().map(|ids| ids.serials.as_slice())
    }

    /// Next birth ordinal, or `None` once identity metadata is exhausted.
    pub(crate) fn next_birth(&self) -> Option<u64> {
        self.identities.as_ref().and_then(|ids| ids.next_birth)
    }

    pub(crate) fn push(&mut self, row: EnemyState) {
        if let Some(ids) = &mut self.identities {
            if let Some(birth) = ids.next_birth {
                ids.serials.push(EnemySerial {
                    namespace: ids.namespace,
                    birth,
                });
                ids.next_birth = birth.checked_add(1);
            } else {
                self.identities = None;
            }
        }
        self.rows.push(row);
    }

    pub(crate) fn remove(&mut self, index: usize) -> EnemyState {
        let row = self.rows.remove(index);
        if let Some(ids) = &mut self.identities {
            ids.serials.remove(index);
        }
        row
    }

    pub(crate) fn clear(&mut self) {
        self.rows.clear();
        if let Some(ids) = &mut self.identities {
            ids.serials.clear();
        }
    }

    pub(crate) fn get_mut(&mut self, index: usize) -> Option<&mut EnemyState> {
        self.rows.get_mut(index)
    }
}

impl Deref for EnemyRows {
    type Target = [EnemyState];

    fn deref(&self) -> &Self::Target {
        self.rows.as_slice()
    }
}

impl<'a> IntoIterator for &'a EnemyRows {
    type Item = &'a EnemyState;
    type IntoIter = std::slice::Iter<'a, EnemyState>;

    fn into_iter(self) -> Self::IntoIter {
        self.rows.iter()
    }
}

impl<'a> IntoIterator for &'a mut EnemyRows {
    type Item = &'a mut EnemyState;
    type IntoIter = std::slice::IterMut<'a, EnemyState>;

    fn into_iter(self) -> Self::IntoIter {
        self.rows.iter_mut()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::PicoFixed;

    fn row() -> EnemyState {
        EnemyState::normal(PicoFixed::ZERO, PicoFixed::ZERO, PicoFixed::from_int(3))
    }

    #[test]
    fn exhaustion_preserves_rows_and_never_recovers_on_clear() {
        let mut rows = EnemyRows {
            rows: Vec::new(),
            identities: Some(IdentityRows {
                namespace: 7,
                next_birth: Some(u64::MAX - 1),
                serials: Vec::new(),
            }),
        };
        rows.push(row());
        rows.push(row());
        let serials = rows.serials();
        assert_eq!(serials.map(<[EnemySerial]>::len), Some(2));
        assert!(serials.is_some_and(|ids| ids.windows(2).all(|w| w.first() < w.last())));
        let valid = rows.clone();
        rows.push(row());
        assert_eq!(rows.len(), 3);
        assert_eq!(rows.serials(), None);
        assert_eq!(rows.remove(0), row());
        assert_eq!(rows.len(), 2);
        rows.clear();
        rows.push(row());
        assert_eq!(rows.len(), 1);
        assert_eq!(rows.serials(), None);
        // Clearing while the final birth is live cannot reset the counter.
        let mut cleared = valid;
        cleared.clear();
        cleared.push(row());
        assert_eq!(cleared.len(), 1);
        assert_eq!(cleared.serials(), None);
    }

    #[test]
    fn namespace_exhaustion_is_sticky_without_touching_game_rng() {
        let counter = AtomicU64::new(u64::MAX - 1);
        assert_eq!(allocate_namespace(&counter), Some(u64::MAX - 1));
        assert_eq!(allocate_namespace(&counter), None);
        assert_eq!(allocate_namespace(&counter), None);
        assert_eq!(counter.load(Ordering::Relaxed), u64::MAX);
        let mut rows = EnemyRows {
            rows: Vec::new(),
            identities: None,
        };
        rows.push(row());
        assert_eq!(rows.len(), 1);
        rows.clear();
        rows.push(row());
        assert_eq!(rows.serials(), None);
    }
}
