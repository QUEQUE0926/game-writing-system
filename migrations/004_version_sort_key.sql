-- 004_version_sort_key.sql — 版本排序字段（用户批准，2026-09-12）
-- 背景：created_at 是"档案登记时间"，不等于"版本真实先后"。
-- 新增 game_versions.sort_key（可空整数）：
--   - 数字小的版本排前面；
--   - 未填（NULL）的版本排后面，按 created_at 兜底；
--   - 老数据零改动，想标谁就标谁。
-- 排序本身是展示/查询约定，不改动任何已有标识符（Level B 新增字段）。

ALTER TABLE game_versions ADD COLUMN sort_key INTEGER;
