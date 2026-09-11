# 05_MATERIAL_CARD_SYSTEM

## 定义

Material Card = 可追溯、可复用的作者亲历素材资产。

## 建议结构

Observation → Experience → Possible Cause → Interpretation → Judgement。

## 建议字段
- subject
- observation
- experience
- possible_cause
- interpretation
- judgement
- quote
- evidence_strength
- writing_value
- author_interest
- reuse_value
- status

## 证据绑定

一张卡可绑定多个 Segment；不得只存自由文本引用。

## 评分原则

不使用单一总分决定命运；当前文章不用不等于长期无价值。

## 人工优先

AI 可建议，作者确认优先级高于模型评分。

## 提炼约定（2026-09-12 新增，针对创作痛点的预制写作零件）

> 依据：`I:\AIstore\8.Gamedata\扁鹊鹊创作痛点研究.md`。核心思路：
> 卡片不是"经历记录"，提炼时就预制成"写作零件"——标题的坯子、开头的料、
> 能独立成段的支线模块。发散脑只负责发散，收束位外化给卡片结构。

### 字段写法约定（不动 Schema，只约定内容）

- **subject = 钩子坯**：15 字以内、带情绪的句子，不写档案标签。
  不写"镇邪Ⅱ开局捏人系统体验"，写"道袍一穿，我成了全村唯一的道士"。
  写作时标题 = 从钩子坯库里挑一个微调，不做从零压缩（痛点一）。
- **quote = 逐字原话**：存作者当时嘴里的原话，依赖 speaker 分类正确
  （区分作者/队友/游戏语音，防止把 NPC 台词错当亲历——事实错误与
  饭味风险的源头）。带高能原话的场景卡天然是开头素材（痛点二）。
- **没有 judgement 的卡不收**：interpretation → judgement 两段是强制
  收束机制，落到"这说明什么/我的判断"才算合格。写文章时插支线 =
  插一张卡，judgement 就是兜回主线的那句话——闭环从脑内负担变成
  查账动作（痛点三）。
- **evidence_strength 高分必须有原话锚点**：保证引用时不用回原文翻找
  核对，省改稿工程（痛点五）。

### 提炼流程约定

1. 一集（Episode）出 1~3 张卡，不贪多：只挑作者情绪最高的瞬间
   （骂了、笑了、惊了），低能片段不入库。
2. AI 只负责提名候选瞬间（哪几段情绪密度高），作者挑选和改写——
   AI 当灵感库不当代笔。
3. 四维评分入库时随手打；写作时按分检索：
   - writing_value 高 → 近期可用池；
   - reuse_value 高 → 跨游戏通用池。

### 对应痛点地图

| 痛点 | 卡片机制 |
|---|---|
| 标题排在精力最低点 | subject 存钩子坯，尾段只挑不改 |
| 开头卡死 | quote 存高能原话，开头有现成第一句 |
| 支线兜不回 | judgement 强制收束，插卡即插模块 |
| 收尾工程塌方 | 评分检索替代记忆翻找 |
