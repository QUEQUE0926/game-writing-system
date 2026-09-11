# 10_CONTEXT_AND_MODEL_ROUTING

## Context Builder

任何模型调用都经过 Context Builder，提供最小阶段性上下文。

Episode：Version 元数据 + 相关 Segment + speaker 信息。
Material Card：Episode + Evidence。
Claim：选中 Material Cards + 必要 Episode / Inspiration。
Outline：Topic + Selected Claims + Selected Assets。
Draft：Outline + Approved Evidence Pack。

## 模型能力层

- T0 确定性代码
- T1 轻量分类
- T2 Episode / Material Card
- T3 Claim / Angle / 跨素材综合
- T4 写作 / 审稿

业务规则不绑定具体模型品牌。
