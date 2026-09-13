-- 005_event_question_thread.sql — V2 创作主线四件套（用户批准，2026-09-14）
-- 背景：17_V2_REDIRECT.md 定案——素材卡降级为临时展示格式，
-- 创作主线改为 Evidence → Event → Question → Thread。
-- 本迁移全部为纯增量新表（Level B 可扩展），老卡表与已有枚举一个不动。
-- 证据只存 segment_id（模型无权持有原话，渲染时由程序取出）。

CREATE TABLE IF NOT EXISTS events (
    id                   TEXT PRIMARY KEY,
    game_version_id      TEXT NOT NULL REFERENCES game_versions(id),
    source_id            TEXT NOT NULL REFERENCES sources(id),
    window_line_start    INTEGER NOT NULL,            -- 窗口/Block 锚点（源内行号）
    level                TEXT NOT NULL
                         CHECK (level IN ('lite','full')),
    title                TEXT NOT NULL,
    event_type           TEXT NOT NULL DEFAULT '[]',  -- JSON 数组，多选
    topics               TEXT NOT NULL DEFAULT '[]',  -- JSON 数组 [{canonical,raw}]
    state_before         TEXT NOT NULL DEFAULT '',
    trigger              TEXT NOT NULL DEFAULT '',
    state_after          TEXT NOT NULL DEFAULT '',
    change_before        TEXT NOT NULL DEFAULT '',    -- Lite 用
    change_after         TEXT NOT NULL DEFAULT '',    -- Lite 用
    experience_chain     TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    core_observation     TEXT NOT NULL DEFAULT '',
    interpretation       TEXT NOT NULL DEFAULT '',
    boundary             TEXT NOT NULL DEFAULT '',    -- 防幻觉：这段证据不能证明什么
    tension              TEXT NOT NULL DEFAULT '',    -- 格式 "A vs B"
    why_valuable         TEXT NOT NULL DEFAULT '',
    possible_question    TEXT NOT NULL DEFAULT '',
    external_fact_needed TEXT NOT NULL DEFAULT '[]',  -- JSON 数组，联网核验后移
    thread_signals       TEXT NOT NULL DEFAULT '[]',  -- JSON 数组 [{type,note}]
    value_level          TEXT NOT NULL
                         CHECK (value_level IN ('HIGH','MEDIUM','LOW')),
    confidence           TEXT NOT NULL
                         CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    model                TEXT NOT NULL DEFAULT '',    -- 溯源 + Event cache 成分
    prompt_version       TEXT NOT NULL DEFAULT '',    -- Event hash 成分（17 文档 §30）
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 纯关系表：Evidence ↔ Event 多对多，证据只存 segment_id
CREATE TABLE IF NOT EXISTS event_evidence (
    event_id   TEXT NOT NULL REFERENCES events(id),
    segment_id TEXT NOT NULL REFERENCES segments(id),
    PRIMARY KEY (event_id, segment_id)
);

CREATE TABLE IF NOT EXISTS questions (
    id                  TEXT PRIMARY KEY,
    game_version_id     TEXT NOT NULL REFERENCES game_versions(id),
    question            TEXT NOT NULL,
    question_type       TEXT NOT NULL
                        CHECK (question_type IN ('design','experience','comparison',
                                                 'mechanism','cause','evaluation')),
    strength            TEXT NOT NULL
                        CHECK (strength IN ('HIGH','MEDIUM','LOW')),
    resolution          TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK (resolution IN ('OPEN','ANSWERED','DROPPED')),
    possible_directions TEXT NOT NULL DEFAULT '[]',   -- JSON 数组
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 纯关系表：Question ↔ Event 多对多
CREATE TABLE IF NOT EXISTS question_events (
    question_id TEXT NOT NULL REFERENCES questions(id),
    event_id    TEXT NOT NULL REFERENCES events(id),
    PRIMARY KEY (question_id, event_id)
);

CREATE TABLE IF NOT EXISTS threads (
    id                     TEXT PRIMARY KEY,
    game_version_id        TEXT NOT NULL REFERENCES game_versions(id),
    title                  TEXT NOT NULL,
    primary_topic          TEXT NOT NULL DEFAULT '',
    central_tension        TEXT NOT NULL DEFAULT '',
    central_question       TEXT NOT NULL DEFAULT '',
    central_question_id    TEXT REFERENCES questions(id),
    start_state            TEXT NOT NULL DEFAULT '',
    end_state              TEXT NOT NULL DEFAULT '',
    turning_point_event_id TEXT REFERENCES events(id),
    experience_arc         TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    potential_thesis       TEXT NOT NULL DEFAULT '',
    closure_target         TEXT NOT NULL DEFAULT '',
    external_fact_needed   TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    maturity               TEXT NOT NULL
                           CHECK (maturity IN ('SEED','DEVELOPING','MATURE')),
    confidence             TEXT NOT NULL
                           CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    status                 TEXT NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active','archived','deprecated','trashed')),
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 纯关系表：Thread ↔ Event 多对多，带体验角色（不是文章段落顺序）
CREATE TABLE IF NOT EXISTS thread_events (
    thread_id TEXT NOT NULL REFERENCES threads(id),
    event_id  TEXT NOT NULL REFERENCES events(id),
    role      TEXT NOT NULL
              CHECK (role IN ('setup','development','turning_point','payoff',
                              'supporting','counterexample','branch')),
    PRIMARY KEY (thread_id, event_id)
);

-- 便宜模型聚合用：Event 两两关系（MVP Thread 聚合的输入）
CREATE TABLE IF NOT EXISTS event_relations (
    id              TEXT PRIMARY KEY,
    game_version_id TEXT NOT NULL REFERENCES game_versions(id),
    from_event_id   TEXT NOT NULL REFERENCES events(id),
    to_event_id     TEXT NOT NULL REFERENCES events(id),
    relation        TEXT NOT NULL
                    CHECK (relation IN ('SAME','DEVELOPS','CONTRADICTS','CAUSES',
                                        'SUPPORTS','PARALLEL','UNRELATED')),
    same_thread     INTEGER NOT NULL DEFAULT 0,
    confidence      TEXT NOT NULL
                    CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    model           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (from_event_id <> to_event_id)
);
