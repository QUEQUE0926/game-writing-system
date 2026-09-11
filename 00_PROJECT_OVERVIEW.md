# 游戏体验素材资产与写作辅助系统
## 总体设计方案 v1.0

## 1. 项目定位

系统目标：将确定游戏和版本下的长篇游戏实况，加工成可追溯、可检索、可跨游戏复用的体验素材资产，并利用 AI 帮助作者完成“体验 → 素材 → 观点 → 角度 → 结构”的收束。

系统不是自动评测生成器，不是稿件管理 CRM，也不是独立长期记忆系统。

核心职责：
- 提炼：长实况 → 真正值得保留的体验素材
- 联想：当前素材 → 历史游戏 / 同系列 / 外部灵感
- 收束：素材 → Claim → Angle → Topic → Outline

## 2. 总体架构

长期资产域：

Series → Game → Version → Source → Segment → Episode → Material Card

Material Card 与 Inspiration Card 通过 Tag / Cross Reference / Usage Record 建立复用关系。

当前创作域：

Project → Asset Recall → Claim → Angle → Topic → Outline → Article → Author Manuscript

长期保存的对象：Series / Game / Version / Source / Segment / Episode / Material Card / Inspiration Card / Tag / Cross Reference / Usage Record。

当前文章工作对象：Project / Claim / Angle / Topic / Outline / Article。

## 3. 游戏身份模型

正式采用：Series（可选）→ Game → Version。

不把 Snapshot / Session / Folder 作为正式业务层。

Version 可以表示 Demo、EA、1.0、DLC、重大更新、首次体验、重新体验等。

Game、Version 由用户创建时明确指定，系统不自动猜测。

## 4. 文件系统

物理目录按 Game → Version 组织，但路径不是身份；稳定 ID 才是身份。

建议：

```text
workspace/
├─ games/
├─ attachments/
├─ exports/
├─ backups/
└─ logs/
```

## 5. Source 与 merged TXT

多个 TXT 可由用户自行合并为 merged.txt，系统将 merged.txt 直接视为一个 Source。

关系：Version → Source → Segment。

Source 保存 source_id、version_id、filename、relative_path、source_type、sha256、encoding、status、imported_at。

Raw Source 默认不可被模型修改。

## 6. Segment 与内部归因

Segment 是稳定证据锚点，只回答“原始证据在哪里”。

需识别 author / teammate / NPC / UI / subtitle / game audio / unrelated chat / ASR error 等内部角色和内容类型，避免误归因。

Unknown 永远允许存在。

## 7. Episode

Episode 表示一段相对完整的体验过程。

- Segment：证据在哪里
- Episode：这段经历发生了什么
- Material Card：这段经历有什么值得以后使用

Moment 暂不作为独立数据库对象，可作为 Episode 内部分析结构。

## 8. Material Card

Material Card 是系统最重要的长期资产。

推荐逻辑：Observation → Experience → Possible Cause → Interpretation → Judgement。

建议字段：subject、observation、experience、possible_cause、interpretation、judgement、quote、evidence_strength、writing_value、author_interest、reuse_value、status。

一张 Material Card 可由多个 Segment 支撑，通过 material_card_evidence 建立多对多关系。

取消单一 15 分制作为核心规则，至少拆分证据强度、写作价值、作者兴趣、复用价值。

## 9. Inspiration Card

Material Card = 自己亲历。

Inspiration Card = 外部有明确来源的信息、案例、观点或灵感。

只保存内容、来源、Tag、与其他资产的关系；不建设复杂 Research Workflow。

## 10. Tag 与 Cross Reference

Tag 用于机制、体验、分析、写作用途等维度。

第一版 Cross Reference 类型建议：similar_to、contrasts、supports、supported_by、extends、contradicts、related_to、inspired_by。

不建设独立长期记忆图谱。

## 11. 素材召回

默认优先级：当前 Version → 当前 Game 其他 Version → 当前 Series 其他 Game → 全库 → Inspiration Card。

再综合 Tag、全文检索、语义相似、Cross Reference、Usage History 排序。

第一版优先 SQLite FTS / Tag / 结构化关系，不急于上向量数据库。

## 12. Project

Project 保持极轻，只表示“当前准备写什么”。

允许 title、关联 games、note 等简单字段，不建设复杂 Brief、甲方管理、DDL 管理或任务风险系统。

## 13. Claim

Claim 是从素材到观点的桥梁，回答“这些经历可能说明什么”。

Claim 必须绑定 supporting Material Cards，不能凭空产生。

Claim 是特定写作语境下的候选解释，不代表作者永久立场。

## 14. Angle 与 Topic

系统在 Claim 之间寻找反差、矛盾、因果、转折、共性、异常，形成 Angle。

Angle = 候选；Topic = 作者确认。

Topic 是正式 Human Gate。

## 15. Outline

Outline 优先建立论证结构，而非简单章节目录。

核心问题 → Claim A/B/C → Evidence → Claim 关系 → 最终判断，再转成文章顺序。

## 16. 写作

Topic → Selected Claims → Outline → Draft / Writing Assistance → Author Manuscript。

AI 可以辅助逻辑检查、支线收束、候选表达、错字检查等；AI Draft 不等于 Author Manuscript。

## 17. Usage Record

Material Card / Inspiration Card 被 Project / Article 使用时创建 Usage Record。

usage_count 从 Usage Record 计算，不手工维护。

## 18. 数据架构

SQLite = 身份、状态、关系、结构化资产。
Filesystem = Raw、附件、缓存、导出。
Markdown = 人类阅读、审核、导出视图。

第一版核心表：series、games、game_versions、sources、segments、episodes、episode_segments、material_cards、material_card_evidence、inspiration_cards、tags、asset_tags、cross_references、usage_records、projects、project_assets、claims、claim_evidence、articles、audit_log、schema_migrations。

## 19. ID 与生命周期

稳定 ID 永不重用。

普通删除：active → archived / deprecated / trashed。

物理删除：Purge → Reference Check → Backup → Confirm → Physical Delete。

## 20. MVP

创建 Series / Game / Version → 导入 merged.txt → Segment → Episode → Material Card → 人工确认 → Tag / Cross Reference → Project → Asset Recall → Claim → Angle → Topic → Outline → Author Manuscript → Usage Record。

## 21. 明确延后

不做：独立长期记忆、Memory Agent、人格画像、复杂 Brief / DDL / CRM、复杂 Research Workflow、复杂发布系统、流量分析、Vector DB、大型知识图谱、自动 Game / Version Resolver、复杂 Moment 模型、强制双写作路线、自动发布。
