# 03_DATA_MODEL

> 本文档按代码现状整理（migrations/001–004 + tests/integration/test_schema_contract.py 快照）。
> 列名快照由该测试钉死，改名会被 verify 拦截；冻结规则见仓库根 AGENTS.md。

## 表清单（按域分组）

### 身份
- series / games / game_versions / game_aliases

### 证据
- sources / segments / episodes / episode_segments

### 素材资产
- material_cards / material_card_evidence / inspiration_cards
- tags / asset_tags / cross_references / usage_records

### 写作
- projects / project_assets / claims / claim_evidence / articles

### 基础设施
- audit_log / schema_migrations

## 各表结构（列名以迁移为准）

### 身份域

**series**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUIDv7 |
| name | TEXT NOT NULL | UNIQUE |
| status | TEXT | active/archived/deprecated/trashed |
| created_at | TEXT | datetime('now') |

**games**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| series_id | TEXT | FK→series(id)，可 NULL（独立游戏） |
| name | TEXT NOT NULL | UNIQUE(series_id, name) |
| status | TEXT | 四态 |
| created_at | TEXT | |

迁移 003 补两个 partial unique index：
- `ux_games_series_name` ON games(series_id, name) WHERE series_id IS NOT NULL
- `ux_games_standalone_name` ON games(name) WHERE series_id IS NULL
（封 SQLite NULL != NULL 的同名漏洞：独立游戏也全库不重名。）

**game_versions**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| game_id | TEXT NOT NULL | FK→games(id) |
| name | TEXT NOT NULL | UNIQUE(game_id, name) |
| status | TEXT | 四态 |
| created_at | TEXT | |
| sort_key | INTEGER | 迁移 004 新增：手动版本序号，可空。小的排前；NULL 排后按 created_at+rowid 兜底。仅影响展示排序，不改数据。经 `gws.py set-version-order` 修改（写 audit_log） |

**game_aliases**（迁移 002 新增）
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| game_id | TEXT NOT NULL | FK→games(id) |
| alias | TEXT NOT NULL | UNIQUE——一个别名只指向一个游戏，构成"游戏名解析字典" |
| created_at | TEXT | |

无 status 列（纯附属表，删除即物理 DELETE）。

### 证据域

**sources**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| version_id | TEXT NOT NULL | FK→game_versions(id) |
| filename | TEXT NOT NULL | |
| relative_path | TEXT NOT NULL | |
| source_type | TEXT | merged_txt / single_txt |
| sha256 | TEXT NOT NULL | UNIQUE(version_id, sha256) 内容指纹去重 |
| encoding | TEXT | 默认 utf-8 |
| status | TEXT | 四态 |
| imported_at | TEXT | |

**segments**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| source_id | TEXT NOT NULL | FK→sources(id) |
| ordinal | INTEGER NOT NULL | UNIQUE(source_id, ordinal)，台词稳定排序键 |
| line_start / line_end | INTEGER NOT NULL | 原文行号，CHECK(line_start <= line_end)，与 ordinal 是两个概念 |
| speaker | TEXT | author/teammate/npc/ui/subtitle/game_audio/unrelated_chat/asr_error/unknown |
| content_type | TEXT | dialogue/narration/ui_text/noise/other |
| text | TEXT NOT NULL | |
| status | TEXT | 四态 |
| created_at | TEXT | |

**episodes**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| version_id | TEXT NOT NULL | FK→game_versions(id) |
| title | TEXT NOT NULL | |
| summary | TEXT | 默认 '' |
| status | TEXT | 四态 |
| created_at | TEXT | |

**episode_segments**（纯关系表，无 status）
| 列 | 类型 | 说明 |
|---|---|---|
| episode_id | TEXT | PK(episode_id, segment_id)，FK→episodes(id) |
| segment_id | TEXT | FK→segments(id) |
| ordinal | INTEGER NOT NULL | |
| position | INTEGER | 迁移 003 新增：证据在集内的展示顺序，`ux_episode_segments_position` UNIQUE(episode_id, position) |

### 素材资产域

**material_cards**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| episode_id | TEXT | FK→episodes(id)，可 NULL |
| subject | TEXT NOT NULL | |
| observation / experience / possible_cause / interpretation / judgement / quote | TEXT | 五段式内容 + 引文，默认 ''（列名 judgement 非 judgment，Level A 冻结） |
| evidence_strength / writing_value / author_interest / reuse_value | INTEGER | 0–5 分，CHECK BETWEEN 0 AND 5 |
| status | TEXT | 四态 |
| created_at | TEXT | |

**material_card_evidence**（纯关系表）
- material_card_id FK→material_cards(id)，segment_id FK→segments(id)，PK(material_card_id, segment_id)

**inspiration_cards**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| title / content | TEXT NOT NULL | |
| source_type / source_ref | TEXT NOT NULL | |
| status | TEXT | 四态 |
| created_at | TEXT | |

**tags**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| name | TEXT NOT NULL | UNIQUE |
| category | TEXT | mechanic/experience/analysis/writing_use/custom |
| status | TEXT | 四态 |

**asset_tags**（纯关系表）
- tag_id FK→tags(id)；asset_type ∈ material_card/inspiration_card；asset_id
- PK(tag_id, asset_type, asset_id)

**cross_references**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| from_type / to_type | TEXT | material_card / inspiration_card |
| from_id / to_id | TEXT NOT NULL | |
| ref_type | TEXT | similar_to/contrasts/supports/supported_by/extends/contradicts/related_to/inspired_by |
| status | TEXT | 四态 |
| created_at | TEXT | |

**usage_records**（只追加，无 status）
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| asset_type / asset_id | TEXT | 被用素材 |
| consumer_type / consumer_id | TEXT | project / article |
| role | TEXT | 默认 'reference' |
| result | TEXT | 默认 '' |
| created_at | TEXT | |

### 写作域

**projects**
- id PK；title NOT NULL；note 默认 ''；status 四态；created_at

**project_assets**（纯关系表）
- project_id FK→projects(id)；asset_type ∈ material_card/inspiration_card；asset_id
- PK(project_id, asset_type, asset_id)

**claims**
- id PK；project_id FK→projects(id) NOT NULL；statement NOT NULL；status 四态；created_at

**claim_evidence**（纯关系表）
- claim_id FK→claims(id)，material_card_id FK→material_cards(id)，PK(claim_id, material_card_id)

**articles**
| 列 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | |
| project_id | TEXT NOT NULL | FK→projects(id) |
| topic | TEXT NOT NULL | |
| outline / draft / manuscript | TEXT | 三阶段文稿，默认 '' |
| status | TEXT | 四态 |
| created_at | TEXT | |

### 基础设施

**audit_log**（只追加）
- id PK；event_name / entity_type / entity_id NOT NULL；detail TEXT 默认 '{}'（JSON）；created_at

**schema_migrations**
- version（PK）、name、applied_at——由 src/gws/migrations.py 管理，禁止绕过。

## ID 规则

内部主键使用 UUIDv7 / ULID 风格 TEXT 稳定 ID；展示名与 ID 分离；ID 一经签发永不复用。

## 生命周期

优先软删除：active / archived / deprecated / trashed（枚举见唯一注册表，AGENTS.md）。

需要 replaced_by 的实体可用于合并或纠错。

Purge 前必须做引用检查与备份。

## 生命周期适用范围

- 长期实体表有 status：series / games / game_versions / sources / segments /
  episodes / material_cards / inspiration_cards / tags / cross_references /
  projects / claims / articles。
- 纯关系/附属表没有 status，删除即物理 DELETE（由 audit_log 留痕）：
  episode_segments / material_card_evidence / asset_tags / claim_evidence /
  project_assets / game_aliases / usage_records / audit_log / schema_migrations。

## 所有关键约束与冻结索引

- 唯一约束见上表；迁移 003 起另强制三个 Level A 冻结索引：
  ux_games_series_name / ux_games_standalone_name / ux_episode_segments_position。
- 外键约束全局开启（PRAGMA foreign_keys=ON，tests/integration/test_migrations.py 验证）。
- Owned-child 关系可受控级联进入 Trash，例如 Version → Source → Segment。
- Reference 关系不得静默级联物理删除，例如 Article → Material Card、
  Material Card → Inspiration Card。

## 枚举值注册表（禁止在代码里另造同义词）

| 字段 | 取值 |
|---|---|
| status | active / archived / deprecated / trashed |
| sources.source_type | merged_txt / single_txt |
| segments.speaker | author / teammate / npc / ui / subtitle / game_audio / unrelated_chat / asr_error / unknown |
| segments.content_type | dialogue / narration / ui_text / noise / other |
| tags.category | mechanic / experience / analysis / writing_use / custom |
| asset_type（asset_tags / usage_records / project_assets） | material_card / inspiration_card |
| cross_references.ref_type | similar_to / contrasts / supports / supported_by / extends / contradicts / related_to / inspired_by |
| usage_records.consumer_type | project / article |

## 命名契约

表名/列名/枚举值的冻结规则见仓库根 AGENTS.md（Level A 冻结 / B 扩展 / C 运行参数）。
列名快照由 tests/integration/test_schema_contract.py 钉死（含 EXPECTED_INDEXES），
改名会被 verify 拦截；新增列须同步更新快照，重命名一律禁止。
