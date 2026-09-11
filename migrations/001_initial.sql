-- 001_initial.sql — 第一版核心表（03_DATA_MODEL）
-- 所有表使用 TEXT 主键（UUIDv7 稳定 ID），软删除状态机 active/archived/deprecated/trashed。

CREATE TABLE IF NOT EXISTS series (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS games (
    id          TEXT PRIMARY KEY,
    series_id   TEXT REFERENCES series(id),
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (series_id, name)
);

CREATE TABLE IF NOT EXISTS game_versions (
    id          TEXT PRIMARY KEY,
    game_id     TEXT NOT NULL REFERENCES games(id),
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (game_id, name)
);

CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,
    version_id    TEXT NOT NULL REFERENCES game_versions(id),
    filename      TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    source_type   TEXT NOT NULL DEFAULT 'merged_txt'
                  CHECK (source_type IN ('merged_txt','single_txt')),
    sha256        TEXT NOT NULL,
    encoding      TEXT NOT NULL DEFAULT 'utf-8',
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','archived','deprecated','trashed')),
    imported_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (version_id, sha256)
);

CREATE TABLE IF NOT EXISTS segments (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    ordinal      INTEGER NOT NULL,
    line_start   INTEGER NOT NULL,
    line_end     INTEGER NOT NULL,
    speaker      TEXT NOT NULL DEFAULT 'unknown'
                 CHECK (speaker IN ('author','teammate','npc','ui','subtitle',
                                    'game_audio','unrelated_chat','asr_error','unknown')),
    content_type TEXT NOT NULL DEFAULT 'dialogue'
                 CHECK (content_type IN ('dialogue','narration','ui_text','noise','other')),
    text         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (line_start <= line_end),
    UNIQUE (source_id, ordinal)
);

CREATE TABLE IF NOT EXISTS episodes (
    id          TEXT PRIMARY KEY,
    version_id  TEXT NOT NULL REFERENCES game_versions(id),
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episode_segments (
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    segment_id TEXT NOT NULL REFERENCES segments(id),
    ordinal    INTEGER NOT NULL,
    PRIMARY KEY (episode_id, segment_id)
);

CREATE TABLE IF NOT EXISTS material_cards (
    id               TEXT PRIMARY KEY,
    episode_id       TEXT REFERENCES episodes(id),
    subject          TEXT NOT NULL,
    observation      TEXT NOT NULL DEFAULT '',
    experience       TEXT NOT NULL DEFAULT '',
    possible_cause   TEXT NOT NULL DEFAULT '',
    interpretation   TEXT NOT NULL DEFAULT '',
    judgement        TEXT NOT NULL DEFAULT '',
    quote            TEXT NOT NULL DEFAULT '',
    evidence_strength INTEGER NOT NULL DEFAULT 0 CHECK (evidence_strength BETWEEN 0 AND 5),
    writing_value    INTEGER NOT NULL DEFAULT 0 CHECK (writing_value BETWEEN 0 AND 5),
    author_interest  INTEGER NOT NULL DEFAULT 0 CHECK (author_interest BETWEEN 0 AND 5),
    reuse_value      INTEGER NOT NULL DEFAULT 0 CHECK (reuse_value BETWEEN 0 AND 5),
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS material_card_evidence (
    material_card_id TEXT NOT NULL REFERENCES material_cards(id),
    segment_id       TEXT NOT NULL REFERENCES segments(id),
    PRIMARY KEY (material_card_id, segment_id)
);

CREATE TABLE IF NOT EXISTS inspiration_cards (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    category   TEXT NOT NULL DEFAULT 'custom'
               CHECK (category IN ('mechanic','experience','analysis','writing_use','custom')),
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','archived','deprecated','trashed'))
);

CREATE TABLE IF NOT EXISTS asset_tags (
    tag_id     TEXT NOT NULL REFERENCES tags(id),
    asset_type TEXT NOT NULL CHECK (asset_type IN ('material_card','inspiration_card')),
    asset_id   TEXT NOT NULL,
    PRIMARY KEY (tag_id, asset_type, asset_id)
);

CREATE TABLE IF NOT EXISTS cross_references (
    id         TEXT PRIMARY KEY,
    from_type  TEXT NOT NULL CHECK (from_type IN ('material_card','inspiration_card')),
    from_id    TEXT NOT NULL,
    to_type    TEXT NOT NULL CHECK (to_type IN ('material_card','inspiration_card')),
    to_id      TEXT NOT NULL,
    ref_type   TEXT NOT NULL
               CHECK (ref_type IN ('similar_to','contrasts','supports','supported_by',
                                   'extends','contradicts','related_to','inspired_by')),
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usage_records (
    id            TEXT PRIMARY KEY,
    asset_type    TEXT NOT NULL CHECK (asset_type IN ('material_card','inspiration_card')),
    asset_id      TEXT NOT NULL,
    consumer_type TEXT NOT NULL CHECK (consumer_type IN ('project','article')),
    consumer_id   TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'reference',
    result        TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_assets (
    project_id TEXT NOT NULL REFERENCES projects(id),
    asset_type TEXT NOT NULL CHECK (asset_type IN ('material_card','inspiration_card')),
    asset_id   TEXT NOT NULL,
    PRIMARY KEY (project_id, asset_type, asset_id)
);

CREATE TABLE IF NOT EXISTS claims (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    statement  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id         TEXT NOT NULL REFERENCES claims(id),
    material_card_id TEXT NOT NULL REFERENCES material_cards(id),
    PRIMARY KEY (claim_id, material_card_id)
);

CREATE TABLE IF NOT EXISTS articles (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    topic      TEXT NOT NULL,
    outline    TEXT NOT NULL DEFAULT '',
    draft      TEXT NOT NULL DEFAULT '',
    manuscript TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    event_name  TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
