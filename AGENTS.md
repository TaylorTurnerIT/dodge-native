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

# Cloud training result safety

DODGE-062 lost its final result download before our coordinator released the VM. Never reuse that
dispatcher for another run. Preserve its failed record, evidence and exact held lease.

Any future cloud training dispatcher must integrate the result-custody successor in
`learning/experiments/teacher_colab_result_safety_20261031_r1` and satisfy these gates:

- Before any native constructor, complete a real 32 MiB upload/export/download/readback rehearsal on
  the exact assigned VM and destination. CPU fixtures alone do not satisfy this gate.
- Copy each saved checkpoint and its update journal off the VM during training. Verify bytes and
  hashes, fsync files and directories, read back, and acknowledge the exact export before continuing.
  Mirror each completed job's worker/supervisor receipts before opening the next job.
- Require a durable remote stage exit receipt with identity, direct reap and process-group absence.
  CLI exit0 or printed output never proves remote success. Preserve safe HTTP status/error class and
  phase without publishing private proxy URLs, tokens, raw config or exception text.
- Fetch bounded immutable chunks rather than depending on one large final archive. Preserve first
  failures and partial copies. A transfer failure never authorizes retrying training or resetting claims.
- Normal VM release requires verified local copies of every required checkpoint and strict terminal
  evidence. Do not release merely because a download failed. Financial/resource/ownership limits stay
  finite: a registered emergency release must first stop work and durably record recovered boundaries
  and data still at risk. Do not keep a GPU indefinitely or relax caps to hide recovery failure.
  If the audit destination itself fails, report that missing audit explicitly and honor the hard cap.
- Test the integrated real producer, transfer process, durable writer, acknowledgment barrier and
  release path with CPU fault fixtures. Independently review the exact future registration and source;
  qualify live transfer throughput inside its existing budget before training. No automatic launch,
  resume, retry, lease clearing or budget increase follows from this source repair.
