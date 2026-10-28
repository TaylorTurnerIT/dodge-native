# Research continuity

Before Dodge experiment planning or interpreting results, consult the local research notebook:

```sh
python/.venv/bin/python -B learning/scripts/research_log.py init
python/.venv/bin/python -B learning/scripts/research_log.py context "relevant question"
```

SQLite (`learning/research/research.sqlite3`) is the working notebook; `learning/research/records.json`
is the tracked restore snapshot. Initialization restores it only into an empty database. Preserve local
changes when a newer snapshot arrives; do not delete the database to synchronize it.

Record each experiment's doing, expected, actual, and why fields. Write predictions before execution;
label late or historical predictions honestly. Leave unobserved results null. Link measured findings to
evidence and follow-ups with `parent_id`. Update through the CLI with the current revision and a reason;
commit the resulting JSON snapshot with relevant source/evidence. See `learning/research/README.md`.

Discuss concepts and competing hypotheses in chat. Use records to preserve knowledge, not replace discussion.
Verify time-sensitive context against current receipts. Database status never authorizes launches, retries,
seed use, or checkpoint promotion. Preserve active training and frozen packages during notebook work.
