CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    catalog TEXT NOT NULL,
    label TEXT NOT NULL,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    release_year INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES releases(id),
    artist TEXT NOT NULL,
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mix_files (
    id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(id),
    mix_type TEXT NOT NULL,
    object_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qc_jobs (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES releases(id),
    track_id TEXT NOT NULL REFERENCES tracks(id),
    mix_file_id TEXT NOT NULL REFERENCES mix_files(id),
    status TEXT NOT NULL,
    error TEXT,
    result JSONB,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
