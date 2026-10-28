CREATE TABLE experiments (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL CHECK (length(trim(project)) > 0),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    status TEXT NOT NULL CHECK (status IN ('planned','conditional','running','completed','failed','blocked','cancelled')),
    doing TEXT NOT NULL CHECK (length(trim(doing)) > 0),
    expected TEXT NOT NULL CHECK (length(trim(expected)) > 0),
    actual TEXT,
    why TEXT,
    next_step TEXT,
    actual_kind TEXT NOT NULL CHECK (actual_kind IN ('unobserved','progress','observed','audited')),
    prediction_timing TEXT NOT NULL CHECK (prediction_timing IN ('before_run','during_run','retrospective','unspecified')),
    parent_id TEXT REFERENCES experiments(id) DEFERRABLE INITIALLY DEFERRED,
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json) AND json_type(tags_json) = 'array'),
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
    revision INTEGER NOT NULL CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (parent_id IS NULL OR parent_id != id),
    CHECK ((actual_kind = 'unobserved' AND actual IS NULL) OR
           (actual_kind != 'unobserved' AND actual IS NOT NULL AND length(trim(actual)) > 0)),
    CHECK (status NOT IN ('completed','failed') OR actual_kind IN ('observed','audited'))
);
CREATE INDEX experiments_project_status ON experiments(project, status);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    kind TEXT NOT NULL CHECK (kind IN ('plan','source','registration','audit','result','progress','note')),
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    uri TEXT NOT NULL CHECK (length(trim(uri)) > 0),
    sha256 TEXT CHECK (sha256 IS NULL OR (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*')),
    recorded_at TEXT NOT NULL
);
CREATE INDEX evidence_experiment ON evidence(experiment_id);

CREATE TABLE measurements (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    model TEXT NOT NULL,
    metric TEXT NOT NULL CHECK (length(trim(metric)) > 0),
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    cohort TEXT,
    sample_count INTEGER CHECK (sample_count IS NULL OR sample_count > 0),
    recorded_at TEXT NOT NULL
);
CREATE INDEX measurements_lookup ON measurements(experiment_id, metric);

CREATE TABLE revisions (
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    revision INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    PRIMARY KEY (experiment_id, revision)
);
CREATE TRIGGER revisions_no_update BEFORE UPDATE ON revisions BEGIN
    SELECT RAISE(ABORT, 'revision history is append-only');
END;
CREATE TRIGGER revisions_no_delete BEFORE DELETE ON revisions BEGIN
    SELECT RAISE(ABORT, 'revision history is append-only');
END;

CREATE TABLE project_context (
    project TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    source_uri TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (project, key)
);

CREATE VIRTUAL TABLE experiment_search USING fts5(
    id UNINDEXED, title, doing, expected, actual, why, next_step, tags_json,
    content='experiments', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER experiment_search_insert AFTER INSERT ON experiments BEGIN
    INSERT INTO experiment_search(rowid,id,title,doing,expected,actual,why,next_step,tags_json)
    VALUES(new.rowid,new.id,new.title,new.doing,new.expected,new.actual,new.why,new.next_step,new.tags_json);
END;
CREATE TRIGGER experiment_search_delete AFTER DELETE ON experiments BEGIN
    INSERT INTO experiment_search(experiment_search,rowid,id,title,doing,expected,actual,why,next_step,tags_json)
    VALUES('delete',old.rowid,old.id,old.title,old.doing,old.expected,old.actual,old.why,old.next_step,old.tags_json);
END;
CREATE TRIGGER experiment_search_update AFTER UPDATE ON experiments BEGIN
    INSERT INTO experiment_search(experiment_search,rowid,id,title,doing,expected,actual,why,next_step,tags_json)
    VALUES('delete',old.rowid,old.id,old.title,old.doing,old.expected,old.actual,old.why,old.next_step,old.tags_json);
    INSERT INTO experiment_search(rowid,id,title,doing,expected,actual,why,next_step,tags_json)
    VALUES(new.rowid,new.id,new.title,new.doing,new.expected,new.actual,new.why,new.next_step,new.tags_json);
END;
PRAGMA user_version = 1;
