# 16_ACCEPTANCE_PLAN

## 业务验收

- 能从真实 merged TXT 建立 Source / Segment / Episode
- 关键 Material Card 可在 2 分钟内追溯到原始证据
- 不把明确 NPC / 队友 / UI 当作者观点
- 能跨 Version / Game / Series 召回历史素材
- Claim 必须有素材依据
- Angle / Outline 能帮助从发散素材收束到可写结构
- Material / Inspiration 可被 Usage Record 追踪复用

## 工程验收

- 新环境可一键初始化
- DEV / TEST / PROD 数据物理隔离
- 历史数据库可通过 migration 升级
- 失败写操作可回滚
- 危险操作自动备份
- Golden Project 全通过
- verify 一键通过
- main 分支始终可运行

## Definition of Done

功能实现 + 数据兼容 + 测试 + 文档 + verify 全部通过，才算完成。
