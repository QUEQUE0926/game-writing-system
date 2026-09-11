-- 002_game_aliases.sql — 游戏别名表
-- 一个游戏可挂多个展示别名（中文名/英文名/俗称）；
-- alias 全局唯一（一个别名只指向一个游戏），匹配时按系列限定范围。

CREATE TABLE IF NOT EXISTS game_aliases (
    id         TEXT PRIMARY KEY,
    game_id    TEXT NOT NULL REFERENCES games(id),
    alias      TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
