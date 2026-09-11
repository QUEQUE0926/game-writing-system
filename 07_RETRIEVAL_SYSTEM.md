# 07_RETRIEVAL_SYSTEM

## 已实现：find 名字解析

`gws find <名字>`：模糊查 系列/游戏/版本，多命中并排显示完整门牌
（系列 → 游戏 → 版本）+ 稳定 id + 别名标注；命中多个同名异人时并排展示由人挑选，
绝不擅自猜一个。任何"按名字操作"前应先 find 确认门牌，再拿 id 干活。

## 召回优先级

当前 Version → 当前 Game 其他 Version → 当前 Series 其他 Game → 全库 → Inspiration Card。

## 第一版手段

- Tag
- SQLite FTS
- Cross Reference
- Usage History
- 结构化字段过滤

向量检索延后，只有当关键词和结构化检索无法满足语义召回时再评估。

## 原则

召回只提供候选，不自动宣称“作者长期观点”。
