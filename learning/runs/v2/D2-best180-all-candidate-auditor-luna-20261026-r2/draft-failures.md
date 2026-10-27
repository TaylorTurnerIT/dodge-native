# Retained draft failures

- First provisional draft failed at frozen-source lookup with `KeyError` because parent reconciliation keys are workspace-relative. Fixed lookup to use paths relative to workspace root; kept the parent pin check.
- Second provisional draft rejected real update-192 progress because the source checkpoint includes optimizer phase details in `update_progress`. Fixed validation to require complete update fields and retain exact metric-to-checkpoint progress equality.

Both failures occurred before any audit result was written. Final pinned CPU provisional pass succeeded. No run output, candidate, parent, sidecar, receipt, lease, or training state was modified.
