-- 003_schema_hardening.sql — 结构加固（外部审查采纳项）
-- 1) games 独立游戏（series_id IS NULL）同名漏洞：
--    SQLite 中 NULL != NULL，表级 UNIQUE(series_id, name) 挡不住
--    两个 NULL 系列的同名游戏 → 用 partial unique index 补齐。
-- 2) episode_segments 增加 position（证据在集内的展示顺序），
--    并约束同一集内 position 不重复。旧行 position 为 NULL 不参与唯一约束。

CREATE UNIQUE INDEX IF NOT EXISTS ux_games_series_name
    ON games(series_id, name)
    WHERE series_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_games_standalone_name
    ON games(name)
    WHERE series_id IS NULL;

ALTER TABLE episode_segments ADD COLUMN position INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS ux_episode_segments_position
    ON episode_segments(episode_id, position);
