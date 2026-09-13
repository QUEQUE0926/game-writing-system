# AGENTS.md — AI 助手数据库契约规则

本仓库的数据库结构是对外兼容契约。任何 AI（包括未来的你）在改动前必须先读本文件。

## 硬性禁令（没有例外）

**禁止：**
- 重命名任何已存在的表名、列名（哪怕你觉得"更合理"）；
- 修改已存在的枚举值/字符串标识（如 status 的 active/archived/deprecated/trashed、speaker 的 8 个分类、ref_type 的 8 种关系）；
- 更改主键语义、复用已删除对象的 id；
- 删除已有列；
- 更改外键的指向关系；
- 为应用结构变更而重建数据库；
- 绕过 Migration 直接用 PRAGMA / sqlite3 CLI 修改线上库结构。

**所有结构变更必须：**
1. 保留已有标识符，只增不破；
2. 通过新的编号迁移文件实现（`migrations/NNN_说明.sql`，编号顺延）；
3. 通过完整 verify（含迁移新建 + 重放、单元、集成、Golden、冒烟、完整性七步）。

## 命名稳定性分级

- **Level A 冻结**：表名、主键、核心外键、核心业务字段（如 material_cards 的
  observation/experience/possible_cause/interpretation/judgement、
  evidence_strength/writing_value/author_interest/reuse_value）、枚举值。
  禁止改名。觉得难看？写文档记录异议，不许动手。
  **丑但稳定的命名，优于破坏兼容的漂亮命名。**
- **Level B 可扩展**：新增字段、新增索引、新增辅助表——正常 Migration 即可。
- **Level C 运行参数**：prompt、模型名、阈值、chunk 大小等放 config，与数据库契约无关，
  不要写死进 Schema，也不要为此改表。

## 唯一注册表（枚举值以此为准，禁止在代码里另造同义词）

- **status（长期实体）**: active / archived / deprecated / trashed
- **speaker**: author / teammate / npc / ui / subtitle / game_audio / unrelated_chat / asr_error / unknown
- **content_type**: dialogue / narration / ui_text / noise / other
- **cross_reference ref_type**: similar_to / contrasts / supports / supported_by / extends / contradicts / related_to / inspired_by
- **sources.source_type**: merged_txt / single_txt
- **tags.category**: mechanic / experience / analysis / writing_use / custom
- **asset_type**（asset_tags / project_assets / usage_records / cross_references 的 from_type / to_type）: material_card / inspiration_card
- **usage_records.consumer_type**: project / article
- **events.level**: lite / full（迁移 005，2026-09-14）
- **V2 通用三档**（events.value_level、events.confidence、questions.strength、threads.confidence、event_relations.confidence）: HIGH / MEDIUM / LOW
- **events.event_type**（多选，JSON 数组存储）: emotion_shift / mechanism_learning / opinion_change / expectation_gap / failure / breakthrough / strategy_change / build_formation / difficulty / progression / usability / balance / narrative_response / performance_issue / other
- **questions.question_type**: design / experience / comparison / mechanism / cause / evaluation
- **questions.resolution**（与长期实体 status 列并存，互不占位）: OPEN / ANSWERED / DROPPED
- **threads.maturity**: SEED / DEVELOPING / MATURE
- **thread_events.role**（体验角色，不是文章段落顺序）: setup / development / turning_point / payoff / supporting / counterexample / branch
- **event_relations.relation**: SAME / DEVELOPS / CONTRADICTS / CAUSES / SUPPORTS / PARALLEL / UNRELATED

## 遇到拿不准的事

宁可停下来写 REVIEW_REQUEST.md 说明阻塞，也不要"顺手优化"结构。
稳定 > 优雅。
