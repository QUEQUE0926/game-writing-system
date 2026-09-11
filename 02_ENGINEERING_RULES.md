# 02_ENGINEERING_RULES

本文件为工程开发契约。任何开发者或 AI Agent 修改项目前必须先阅读。

## 1. 总原则

数据先于功能；迁移代替重建；验证代替肉眼；小步修改代替大爆炸式重构；事故必须转化成测试。

## 2. 环境隔离

至少区分 DEV / TEST / PROD。

必须同时隔离：SQLite、Raw storage、Config、Cache、Exports、Logs、Temp、Credentials。

禁止仅修改程序名而共用真实数据。

## 3. Schema Migration

数据库从第一天带 schema version。

使用 migrations/001_initial.sql、002_xxx.sql... 与 schema_migrations 表。

禁止删除 app.db 后重建作为正式升级方案。

所有 migration 必须在测试数据库和 Golden Project 上验证。

表名/列名/枚举值是冻结契约：硬规则见仓库根 AGENTS.md（Level A 禁止 rename，
枚举以唯一注册表为准）；机器验收由 tests/integration/test_schema_contract.py
的列名快照承担，任何改名都会让 verify FAIL。

## 4. 数据写入

复杂写操作必须：Validate → BEGIN → Write → COMMIT；失败 ROLLBACK。

LLM 输出必须先经过 JSON/Schema Validation、Reference Validation、Domain Validation，才能进入正式表。

## 5. 数据不变量

尽可能用 FOREIGN KEY / UNIQUE / CHECK / Validator / Automated Test 落地。

至少保证：
- Version 属于存在的 Game
- Source 属于存在的 Version
- Segment 属于存在的 Source
- Material Card Evidence 指向有效 Segment
- Cross Reference 两端存在
- Usage Record 指向有效资产
- 稳定 ID 不复用
- Raw 不被静默修改
- trashed 对象不能接收新的正常引用
- 明确 NPC / teammate 内容不能作为作者证据

## 6. 代码依赖方向

UI / CLI → Application → Domain → Repository → SQLite。

Application 可调用 AI Adapter / Storage Adapter / Search Adapter。

Domain 不依赖模型品牌、UI、CLI、数据库路径。

## 7. AI 可替换、可失败

业务层定义能力接口，例如 EpisodeExtractor、MaterialCardExtractor、ClaimGenerator、AngleGenerator、OutlineAssistant。

具体模型实现可替换。

模型失败只令任务 FAILED，并记录日志；不得破坏已有正式数据，也不得阻止浏览旧数据。

## 8. Golden Project

从 MVP 第一阶段建立 tests/fixtures/golden_project/。

覆盖：作者评价、NPC、队友、UI朗读、ASR错误、重复情绪、体验反转、Material Card、Claim、Cross Reference。

每次修改执行完整链路 Import → Segment → Episode → Material Card → Claim → Project。

每个严重 Bug 的修复必须新增回归用例。

## 9. 一键验收

项目必须提供统一 verify 入口，一次执行：
- Schema check
- Migration test
- Unit tests
- Integration tests
- Golden Project
- Import smoke test
- DB integrity check

只有 ALL CHECKS PASSED 才算基础验收通过。

## 10. Git 规则

main 始终可运行；功能开发使用 dev / feature/*。

每个重要 commit 都必须可 checkout、可运行、可 verify。

禁止长时间大重构后最后一次性测试。

## 11. 重构模式

使用 Expand → Migrate → Switch → Contract。

不要先删旧字段再全项目追改。

## 12. 备份与恢复

Migration、Bulk Import、Bulk Regenerate、Merge Game、Purge 前自动备份。

恢复时将坏库重命名为 .damaged-<timestamp> 保存，不覆盖现场。

## 13. 日志与审计

关键事件一行一个并带稳定事件名；日志应能直接支持测试断言和问题定位。

重要状态变化可写入 audit_log。

## 14. Definition of Done

Feature 完成必须同时满足：
- 功能可运行
- Schema / Migration 正确
- 自动测试通过
- Golden Project 通过
- 旧数据兼容
- 关键错误可观察
- 文档同步
- verify 一键通过

涉及数据修改时，还需验证失败回滚、旧数据恢复、引用完整性。
