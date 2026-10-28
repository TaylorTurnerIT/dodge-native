"""Local experiment memory: SQLite, literal full-text retrieval, immutable revisions, and portable JSON snapshots.

No Torch, model API, training controller, or background service is imported. The database records research;
its contents never grant permission to run an experiment or promote a checkpoint.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import uuid

DIRECTORY = Path(__file__).resolve().parents[1] / 'research'
DEFAULT_DB = DIRECTORY / 'research.sqlite3'
DEFAULT_SNAPSHOT = DIRECTORY / 'records.json'
SCHEMA = DIRECTORY / 'schema.sql'
FIELDS = ('id', 'project', 'title', 'status', 'doing', 'expected', 'actual', 'why', 'next_step',
          'actual_kind', 'prediction_timing', 'parent_id', 'tags_json', 'metadata_json',
          'revision', 'created_at', 'updated_at')
EDITABLE = set(FIELDS) - {'id', 'revision', 'created_at', 'updated_at', 'tags_json', 'metadata_json'} | {'tags', 'metadata'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def publish_json(path, value):
    """Atomically replace the portable snapshot after the SQLite transaction commits."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(staging, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


class Store:
    def __init__(self, path, *, initialize=False):
        self.path = Path(path)
        require(initialize or self.path.is_file(), 'Database missing; run the init command first.')
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA busy_timeout=5000')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if initialize and version == 0:
                require(not self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                        'Refusing to initialize an existing unrelated database.')
                self.db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA.read_text() + '\nCOMMIT;')
                version = 1
            require(version == 1, f'Unsupported research database version: {version}')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def get(self, experiment_id, *, history=False):
        row = self.db.execute('SELECT * FROM experiments WHERE id=?', (experiment_id,)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        result = dict(row)
        result['tags'] = json.loads(result.pop('tags_json'))
        result['metadata'] = json.loads(result.pop('metadata_json'))
        for table in ('evidence', 'measurements'):
            result[table] = [dict(r) for r in self.db.execute(
                f'SELECT * FROM {table} WHERE experiment_id=? ORDER BY id', (experiment_id,))]
        if history:
            result['history'] = self.history(experiment_id)
        return result

    def history(self, experiment_id):
        result = []
        for row in self.db.execute('SELECT * FROM revisions WHERE experiment_id=? ORDER BY revision', (experiment_id,)):
            value = dict(row)
            value['snapshot'] = json.loads(value.pop('snapshot_json'))
            result.append(value)
        return result

    def _validate(self, record):
        for key in ('id', 'project', 'title', 'doing', 'expected'):
            require(isinstance(record.get(key), str) and bool(record[key].strip()), f'{key} must be nonempty text')
        require(isinstance(record['tags'], list) and all(isinstance(t, str) for t in record['tags']), 'tags must be strings')
        require(isinstance(record['metadata'], dict), 'metadata must be an object')
        actual = record.get('actual')
        if record['actual_kind'] == 'unobserved':
            require(actual is None, 'Unobserved experiments cannot contain a result; use progress or observed.')
        else:
            require(isinstance(actual, str) and bool(actual.strip()), 'An observation kind requires result text.')
        if record['status'] in {'completed', 'failed'}:
            require(bool(record.get('actual')) and record['actual_kind'] in {'observed', 'audited'},
                    'Finished experiments need observed results, not predictions.')
            require(bool(record.get('evidence')), 'Finished experiments need an evidence reference.')
        if record['actual_kind'] == 'audited':
            require(any(e['kind'] == 'audit' and e.get('sha256') for e in record.get('evidence', [])),
                    'Audited results need a hash-pinned audit reference.')

    def _insert_children(self, experiment_id, evidence, measurements):
        for item in evidence:
            value = dict(item)
            require(value.get('experiment_id', experiment_id) == experiment_id, 'Evidence belongs to another experiment.')
            value.update(id=value.get('id', uuid.uuid4().hex), experiment_id=experiment_id,
                         recorded_at=value.get('recorded_at', now()))
            names = ('id', 'experiment_id', 'kind', 'label', 'uri', 'sha256', 'recorded_at')
            self.db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?)', tuple(value.get(k) for k in names))
        for item in measurements:
            value = dict(item)
            require(value.get('experiment_id', experiment_id) == experiment_id, 'Measurement belongs to another experiment.')
            require(type(value.get('value')) in (int, float) and math.isfinite(value['value']), 'Measurement must be finite.')
            evidence_row = self.db.execute('SELECT experiment_id FROM evidence WHERE id=?', (value['evidence_id'],)).fetchone()
            require(evidence_row is not None and evidence_row[0] == experiment_id, 'Measurement evidence must belong to its experiment.')
            value.update(id=value.get('id', uuid.uuid4().hex), experiment_id=experiment_id,
                         recorded_at=value.get('recorded_at', now()))
            names = ('id', 'experiment_id', 'evidence_id', 'model', 'metric', 'value', 'unit', 'cohort', 'sample_count', 'recorded_at')
            self.db.execute('INSERT INTO measurements VALUES (?,?,?,?,?,?,?,?,?,?)', tuple(value.get(k) for k in names))

    def _revision(self, experiment_id, *, actor, reason):
        require(bool(reason.strip()), 'A revision reason is required.')
        record = self.get(experiment_id)
        self.db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',
                        (experiment_id, record['revision'], record['updated_at'], actor, reason, encoded(record)))

    def _insert_record(self, value):
        self._validate(value)
        sql = {**value, 'tags_json': encoded(value['tags']), 'metadata_json': encoded(value['metadata'])}
        self.db.execute('INSERT INTO experiments VALUES (' + ','.join('?' for _ in FIELDS) + ')', tuple(sql[k] for k in FIELDS))
        self._insert_children(value['id'], value['evidence'], value['measurements'])

    def _create(self, record, *, actor, reason):
        value = dict(record)
        value.pop('history', None)
        stamp = now()
        defaults = dict(id=uuid.uuid4().hex, status='planned', actual=None, why=None, next_step=None,
                        actual_kind='unobserved', prediction_timing='before_run', parent_id=None, tags=[], metadata={},
                        revision=1, created_at=stamp, updated_at=stamp, evidence=[], measurements=[])
        value = {**defaults, **value}
        require(set(value) <= (set(FIELDS) - {'tags_json', 'metadata_json'} | {'tags', 'metadata', 'evidence', 'measurements'}),
                'Unknown experiment fields.')
        self._insert_record(value)
        self._revision(value['id'], actor=actor, reason=reason)
        return value['id']

    def create(self, record, *, actor='agent', reason):
        require(record.get('revision', 1) == 1, 'New experiments start at revision 1.')
        with self.transaction():
            experiment_id = self._create(record, actor=actor, reason=reason)
        return self.get(experiment_id)

    def update(self, experiment_id, patch, *, expected_revision, actor='agent', reason):
        require(set(patch) <= EDITABLE | {'evidence', 'measurements'}, 'Unknown or immutable update fields.')
        with self.transaction():
            old = self.get(experiment_id)
            require(old['revision'] == expected_revision, 'Revision conflict; read the current record before updating.')
            if old['status'] not in {'planned', 'conditional'}:
                for key in ('expected', 'prediction_timing'):
                    require(patch.get(key, old[key]) == old[key], 'Prediction is frozen after work starts; create a follow-up experiment.')
                require(patch.get('status') not in {'planned', 'conditional'}, 'Started work cannot return to a planning status.')
            if old['status'] in TERMINAL and 'status' in patch:
                require(patch['status'] == old['status'], 'Do not reopen a finished experiment; create a follow-up.')
            new_evidence, new_measurements = patch.get('evidence', []), patch.get('measurements', [])
            value = {**old, **{k: v for k, v in patch.items() if k in EDITABLE}}
            value['evidence'] = old['evidence'] + new_evidence
            value['revision'], value['updated_at'] = old['revision'] + 1, now()
            self._validate(value)
            sql = {**value, 'tags_json': encoded(value['tags']), 'metadata_json': encoded(value['metadata'])}
            names = [k for k in FIELDS if k != 'id']
            self.db.execute('UPDATE experiments SET ' + ','.join(k + '=?' for k in names) + ' WHERE id=?',
                            (*[sql[k] for k in names], experiment_id))
            self._insert_children(experiment_id, new_evidence, new_measurements)
            self._revision(experiment_id, actor=actor, reason=reason)
        return self.get(experiment_id)

    def list(self, *, project=None, status=None, limit=100):
        clauses, values = [], []
        for key, value in (('project', project), ('status', status)):
            if value is not None:
                clauses.append(key + '=?'); values.append(value)
        query = 'SELECT id FROM experiments' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY id LIMIT ?'
        return [self.get(r[0]) for r in self.db.execute(query, (*values, limit))]

    def search(self, query, *, project=None, limit=10):
        tokens = re.findall(r'\w+', query, flags=re.UNICODE)
        if not tokens:
            return []
        match = ' OR '.join('"' + token + '"' for token in tokens)
        sql = ('SELECT e.id FROM experiment_search JOIN experiments e ON e.rowid=experiment_search.rowid '
               'WHERE experiment_search MATCH ?')
        values = [match]
        if project is not None:
            sql += ' AND e.project=?'; values.append(project)
        sql += ' ORDER BY bm25(experiment_search),e.id LIMIT ?'
        return [self.get(r[0]) for r in self.db.execute(sql, (*values, limit))]

    def context(self, project, query='', *, limit=5):
        rows = self.search(query, project=project, limit=limit) if query else self.list(project=project, limit=1000)
        if not query:
            rows.sort(key=lambda r: (r['status'] != 'running', r['status'] != 'completed', r['id']))
            rows = rows[:limit]
        memory = [dict(project=r['project'], key=r['key'], value=json.loads(r['value_json']),
                       source_uri=r['source_uri'], recorded_at=r['recorded_at'])
                  for r in self.db.execute('SELECT * FROM project_context WHERE project=? ORDER BY key', (project,))]
        fields = ('id', 'title', 'status', 'doing', 'expected', 'actual', 'why', 'next_step', 'actual_kind',
                  'prediction_timing', 'parent_id', 'tags', 'revision', 'updated_at', 'evidence')
        compact = [dict({key: r[key] for key in fields}, measurement_count=len(r['measurements'])) for r in rows]
        return dict(project=project, context=memory, experiments=compact,
                    interpretation='Expected and why are hypotheses, not measured facts. actual_kind labels observation authority. '
                                   'Database records do not authorize launches, retries, or checkpoint promotion.')

    def snapshot(self):
        if not self.db.in_transaction:
            with self.transaction():
                return self.snapshot()
        context = [dict(project=r['project'], key=r['key'], value=json.loads(r['value_json']),
                        source_uri=r['source_uri'], recorded_at=r['recorded_at'])
                   for r in self.db.execute('SELECT * FROM project_context ORDER BY project,key')]
        return dict(schema_version=1, project_context=context,
                    experiments=[self.get(r[0], history=True) for r in self.db.execute('SELECT id FROM experiments ORDER BY id')])

    def export(self, path):
        # Serialize snapshot publication with writers, preventing an older concurrent export from winning.
        require(Path(path).resolve() not in {self.path.resolve(), Path(str(self.path.resolve()) + '-wal'),
                                            Path(str(self.path.resolve()) + '-shm')},
                'A JSON export cannot replace the database or its journal files.')
        with self.transaction():
            publish_json(path, self.snapshot())

    def restore(self, snapshot):
        require(snapshot.get('schema_version') == 1, 'Unsupported snapshot version.')
        with self.transaction():
            require(not self.db.execute('SELECT 1 FROM experiments LIMIT 1').fetchone()
                    and not self.db.execute('SELECT 1 FROM project_context LIMIT 1').fetchone(),
                    'Restore requires an empty database; existing records are never replaced.')
            for record in snapshot['experiments']:
                value = dict(record); history = value.pop('history')
                self._insert_record(value)
                for revision in history:
                    require(revision['experiment_id'] == value['id'], 'History belongs to another experiment.')
                    self.db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',
                        (value['id'], revision['revision'], revision['recorded_at'], revision['actor'],
                         revision['reason'], encoded(revision['snapshot'])))
            for item in snapshot['project_context']:
                self.db.execute('INSERT INTO project_context VALUES (?,?,?,?,?)',
                    (item['project'], item['key'], encoded(item['value']), item['source_uri'], item['recorded_at']))
            self.check()
            require(self.snapshot() == snapshot, 'Restore changed snapshot data.')

    def check(self):
        if not self.db.in_transaction:
            with self.transaction():
                return self.check()
        require(self.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SQLite integrity check failed.')
        require(not self.db.execute('PRAGMA foreign_key_check').fetchall(), 'Foreign key check failed.')
        self.db.execute("INSERT INTO experiment_search(experiment_search,rank) VALUES('integrity-check',1)")
        total = 0
        for row in self.db.execute('SELECT id FROM experiments'):
            record = self.get(row[0]); history = self.history(row[0]); total += 1
            require([r['revision'] for r in history] == list(range(1, record['revision'] + 1)), 'Revision sequence differs.')
            require(history[-1]['snapshot'] == record, 'Latest revision differs from current record.')
            for revision in history:
                previous = revision['snapshot']
                require(previous['id'] == record['id'] and previous['revision'] == revision['revision'],
                        'Revision snapshot identity differs.')
                require(previous['updated_at'] == revision['recorded_at'], 'Revision timestamp differs.')
                self._validate(previous)
            for metric in record['measurements']:
                require(any(e['id'] == metric['evidence_id'] for e in record['evidence']),
                        'Measurement evidence belongs to another experiment.')
            self._validate(record)
        return dict(status='ok', experiments=total, schema_version=1)

    def backup(self, path):
        path = Path(path)
        require(not path.exists(), 'Backup destination already exists.')
        path.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()


def load_json(path):
    return json.loads(sys.stdin.read() if path == '-' else Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--snapshot', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init'); init.add_argument('--from-json', type=Path)
    for name in ('list', 'search', 'context'):
        command = commands.add_parser(name); command.add_argument('--project', default='dodge-native')
        command.add_argument('--limit', type=int, default=10 if name != 'context' else 5)
        if name == 'list':
            command.add_argument('--status')
        else:
            command.add_argument('query', nargs='?' if name == 'context' else None, default='')
    for name in ('show', 'history', 'metrics'):
        command = commands.add_parser(name); command.add_argument('id')
        if name == 'show':
            command.add_argument('--json', action='store_true')
        if name == 'metrics':
            command.add_argument('--metric')
    for name in ('create', 'update'):
        command = commands.add_parser(name)
        if name == 'update':
            command.add_argument('id'); command.add_argument('--expected-revision', type=int, required=True)
        command.add_argument('--input', required=True); command.add_argument('--reason', required=True)
        command.add_argument('--actor', default='agent')
    command = commands.add_parser('export'); command.add_argument('--output', type=Path)
    command = commands.add_parser('backup'); command.add_argument('output', type=Path)
    commands.add_parser('check')
    args = parser.parse_args(argv)
    if hasattr(args, 'limit'):
        require(1 <= args.limit <= 1000, 'Limit must be between 1 and 1000.')
    snapshot_path = args.snapshot or (DEFAULT_SNAPSHOT if args.db.resolve() == DEFAULT_DB.resolve() else args.db.with_suffix('.json'))
    store = Store(args.db, initialize=args.command == 'init')
    try:
        changed = False
        if args.command == 'init':
            seed = args.from_json or snapshot_path
            if seed.exists() and not store.db.execute('SELECT 1 FROM experiments LIMIT 1').fetchone():
                store.restore(load_json(str(seed)))
            result = store.check(); changed = True
        elif args.command == 'create':
            result = store.create(load_json(args.input), actor=args.actor, reason=args.reason); changed = True
        elif args.command == 'update':
            result = store.update(args.id, load_json(args.input), expected_revision=args.expected_revision,
                                  actor=args.actor, reason=args.reason); changed = True
        elif args.command == 'list':
            result = [{key: r[key] for key in ('id', 'title', 'status', 'actual_kind', 'revision')}
                      for r in store.list(project=args.project, status=args.status, limit=args.limit)]
        elif args.command == 'search':
            result = store.context(args.project, args.query, limit=args.limit)['experiments']
        elif args.command == 'context':
            result = store.context(args.project, args.query, limit=args.limit)
        elif args.command == 'show':
            result = store.get(args.id)
            if not args.json:
                print(f"{result['id']}: {result['title']}\nStatus: {result['status']}; revision {result['revision']}; observations: {result['actual_kind']}")
                for key, label in (('doing', "What we're doing:"), ('expected', 'What we expect to happen:'),
                                   ('actual', 'What actually happened:'), ('why', 'Why might it have happened?')):
                    print('\n' + label + '\n' + (result[key] or 'Not observed yet.'))
                return 0
        elif args.command == 'history':
            store.get(args.id); result = store.history(args.id)
        elif args.command == 'metrics':
            result = store.get(args.id)['measurements']
            if args.metric:
                result = [r for r in result if r['metric'] == args.metric]
        elif args.command == 'export':
            target = args.output or snapshot_path; store.export(target); result = dict(exported=str(target))
        elif args.command == 'backup':
            store.backup(args.output); result = dict(backup=str(args.output))
        else:
            result = store.check()
        if changed:
            store.export(snapshot_path)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    finally:
        store.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, sqlite3.Error, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
