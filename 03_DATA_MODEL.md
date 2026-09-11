# 03_DATA_MODEL

## 建议第一版核心表

### 身份
- series
- games
- game_versions
- game_aliases（游戏别名：旧名/中英文名，alias 全库唯一，构成"游戏名解析字典"）

### 证据
- sources
- segments
- episodes
- episode_segments

### 素材资产
- material_cards
- material_card_evidence
- inspiration_cards
- tags
- asset_tags
- cross_references
- usage_records

### 写作
- projects
- project_assets
- claims
- claim_evidence
- articles

### 基础设施
- audit_log
- schema_migrations

## ID 规则

内部主键使用 UUIDv7 / ULID 风格稳定 ID；展示名与 ID 分离；ID 一经签发永不复用。

## 生命周期

优先软删除：active / archived / deprecated / trashed。

需要 replaced_by 的实体可用于合并或纠错。

Purge 前必须做引用检查与备份。

## 所有关系与引用关系

Owned-child 关系可受控级联进入 Trash，例如 Version → Source → Segment。

Reference 关系不得静默级联物理删除，例如 Article → Material Card、Material Card → Inspiration Card。

## 生命周期适用范围

- 长期实体表有 status：series / games / game_versions / sources / episodes /
  material_cards / inspiration_cards / projects / claims / articles。
- 纯关系表没有 status，删除即物理 DELETE（由 audit_log 留痕）：
  episode_segments / material_card_evidence / asset_tags / claim_evidence / project_assets。

## 关键唯一约束（迁移 003 起强制）

- games：同系列内不重名；series_id 为 NULL 的独立游戏也全库不重名
  （partial unique index，封 SQLite NULL != NULL 漏洞）。
- segments：UNIQUE(source_id, ordinal)；ordinal 是台词稳定排序键，
  与原文行号 line_start/line_end 是两个概念，不混用。
- episode_segments：UNIQUE(episode_id, segment_id) + UNIQUE(episode_id, position)
  —— position 表示证据在集内的展示顺序。
- sources：UNIQUE(version_id, sha256)，内容指纹去重。

## 命名契约

表名/列名/枚举值的冻结规则见仓库根 AGENTS.md（Level A 冻结 / B 扩展 / C 运行参数）。
列名快照由 tests/integration/test_schema_contract.py 钉死，改名会被 verify 拦截。
