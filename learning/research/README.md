# Local research notebook

`research.sqlite3` is the working notebook. `records.json` is its versioned, restorable snapshot.
The database, journals, and SQLite backups stay local. No model API, embeddings, or service is required.

Each experiment stores the four agreed questions: what we're doing, what we expect, what happened,
and why it might have happened. Predictions and explanations remain hypotheses. Observations carry
an authority label (`progress`, `observed`, or `audited`), evidence links, and optional numeric measurements.
`audited` requires a hash-pinned audit reference; it does not independently verify the audit's conclusions.

From the repository root:

```sh
# First use in a checkout: restore the tracked snapshot if the local database is missing.
python/.venv/bin/python -B learning/scripts/research_log.py init

# Retrieve compact context before research work; inspect details only when useful.
python/.venv/bin/python -B learning/scripts/research_log.py context "opening control frequency"
python/.venv/bin/python -B learning/scripts/research_log.py list
python/.venv/bin/python -B learning/scripts/research_log.py show DODGE-010
python/.venv/bin/python -B learning/scripts/research_log.py metrics DODGE-010 --metric Q1
```

Create a record with `create --input record.json --reason "Register prediction"`.
Required JSON fields are `id`, `project`, `title`, `doing`, and `expected`; status defaults to `planned`.
Use `parent_id` to connect a follow-up experiment to its predecessor. `tags` aid retrieval.
Set `prediction_timing` honestly: `before_run`, `during_run`, `retrospective`, or `unspecified`.

After reading the current revision, append a result or interpretation:

```sh
python/.venv/bin/python -B learning/scripts/research_log.py update DODGE-002 \
  --expected-revision 1 --input result-patch.json --reason "Record measured result"
```

A result patch can contain `status`, `actual`, `actual_kind`, `why`, `next_step`, `evidence`, and `measurements`.
Evidence entries need `kind`, `label`, and `uri`; provide `id` when measurements reference them.
Measurements need `evidence_id`, `model`, `metric`, `value`, and `unit`; `cohort` and `sample_count` are optional.
Evidence and measurements append; they do not replace prior entries. Use explicit corrections if a prior value was wrong.
Every experiment mutation records the full revision, actor, reason, and UTC timestamp in immutable history.
Stale updates fail. Predictions freeze once work starts. Finished experiments need evidence and observed results.
Create a follow-up rather than reopening a finished experiment. `history ID` retrieves previous revisions.

CLI writes commit to SQLite first, then atomically publish `records.json` under a writer lock.
If snapshot publication fails, the SQLite change remains committed: inspect the revision, then run `export`.
Do not replay the mutation blindly. Snapshot export is also available explicitly:

```sh
python/.venv/bin/python -B learning/scripts/research_log.py check
python/.venv/bin/python -B learning/scripts/research_log.py export
python/.venv/bin/python -B learning/scripts/research_log.py backup learning/research/backups/manual.sqlite3
```

For recovery, restore into a **new** path; restore never replaces a populated database:

```sh
python/.venv/bin/python -B learning/scripts/research_log.py \
  --db /tmp/dodge-recovered.sqlite3 init --from-json learning/research/records.json
```

Tests: `python/.venv/bin/python -B learning/tests/test_research_log.py`.
The one-time importer `learning/scripts/import_research_plan.py` preserves the original plan from commit
`3d43988` and two completed studies with audit references. It refuses to replace an existing snapshot.
The old Markdown plan is an archive, not a second live notebook. Later snapshot commits require deliberate
reconciliation with any existing local database; `init` never overwrites local records.

This notebook stores knowledge. Existing execution gates and checkpoint acceptance still govern experiments.
Add semantic retrieval or a memory framework only if concrete retrieval failures justify the extra complexity.
