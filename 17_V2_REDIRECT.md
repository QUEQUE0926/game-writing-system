# 游戏实况价值语料挖掘与创作辅助系统 V2

## 1. 项目定位

本项目不再以“从游戏实况中批量生产素材卡”为最终目标。

新的核心目标是：

> 从长时间游戏实况中，发现真正值得写的体验变化、矛盾、问题和判断，并将它们组织成能够直接帮助创作启动、展开和收束的素材资产。

系统最终服务的不是“卡片数量”，而是完整创作链：

```text
实况中的一个好瞬间
↓
被系统发现
↓
被正确理解
↓
与其他体验建立联系
↓
形成值得追问的问题
↓
形成创作线索
↓
进入文章
↓
帮助文章完成收束
```

项目需要重点优化的指标不再是：

```text
生成多少卡
```

而是：

```text
强模型时间 / 最终采用洞察

以及

一个有价值体验
→
真正进入文章
之间的损耗
```

---

# 2. 核心设计原则

## 2.1 不提前加工所有素材

旧方案的问题：

```text
发现素材
↓
精读
↓
立刻完整制卡
↓
验收
↓
未来可能用，也可能不用
```

这意味着大量时间消耗在“暂时不知道是否会使用的素材”上。

新版改成：

```text
发现
↓
理解
↓
保存理解
↓
真正创作时再加工
```

原则：

> 先保存认知资产，不提前生产最终制品。

---

## 2.2 强模型只做不可替代的理解工作

强模型负责：

* 理解上下文；
* 判断玩家体验发生了什么变化；
* 找真正值得记录的事件；
* 识别矛盾；
* 判断可能值得追问的问题；
* 判断素材边界；
* 识别多个事件之间的关系。

强模型不负责：

* 卡片格式整理；
* 五维评分展开；
* 原话逐字复制；
* 行号填写；
* speaker 填写；
* 普通格式转换；
* 大量卡片扩写；
* 已知事实重复联网；
* 大规模机械验收。

原则：

> 强模型负责发现价值，不负责包装价值。

---

## 2.3 程序负责“绝对不能错”的内容

以下内容尽量不交给模型：

* 玩家原话；
* segment ID；
* speaker；
* episode；
* 行号；
* timestamp；
* 游戏版本；
* 证据绑定；
* quote 校验；
* 稳定卡号；
* web fact 挂载；
* 状态管理。

模型只能选择：

```text
我要引用 segment 3821
```

程序负责实际取出：

```text
玩家原话
speaker
episode
line
timestamp
```

模型无权修改。

---

## 2.4 AI 不替作者写，重点帮助作者收束

系统需要顺着作者本身的创作方式设计。

作者擅长：

* 发散；
* 联想；
* 吐槽；
* 类比；
* 从具体体验生长观点；
* 写正文。

系统重点承担：

* 记忆；
* 归类；
* 找关系；
* 找矛盾；
* 找问题；
* 提醒支线；
* 提醒兜回；
* 保存原始证据；
* 核验事实；
* 生成标题种子；
* 提供开头入口；
* 检查结尾；
* 收尾工程。

系统定位：

> 外置收束器，而不是 AI 代笔工具。

---

# 3. 整体数据结构

新版核心结构：

```text
Evidence
↓
Event
↓
Question
↓
Thread
↓
Writing Packet
```

Card 不再是核心永久数据结构。

Card 可以继续存在，但只作为：

> Event / Thread 的一种临时展示格式。

---

# 4. 第一层：Evidence

## 4.1 定义

Evidence 是未经解释的原始证据。

回答：

> 当时具体发生了什么、说了什么？

示例：

```yaml
evidence_id: EV_003821

segment_id: 3821

game:
version:
episode:

speaker:
timestamp:

text:
  "那我不是白刷了吗"

window_id: W023
```

## 4.2 特性

Evidence：

* 永不由模型改写；
* 不包含分析；
* 不包含价值判断；
* 可以被多个 Event 重复引用。

## 4.3 来源

直接来自现有：

```text
segments
```

所以现有导入链完全保留。

---

# 5. 第二层：Event

## 5.1 定义

Event 是整套系统最重要的数据对象。

Event 表示：

> 玩家体验、认知、情绪、策略或判断发生了一次值得记录的变化。

不是“说了一句话”，而是：

```text
之前怎么想
↓
发生什么
↓
后来怎么想
```

---

## 5.2 Event Full

高价值事件保存完整结构：

```yaml
event_id: EVT_0023

title:
  升级后没有产生预期中的成长感

type:
  - mechanism_learning
  - expectation_gap
  - opinion_change

topic:
  成长系统

state_before:
  玩家期待升级能够明显降低战斗压力

trigger:
  升级后继续进入战斗

state_after:
  玩家开始怀疑此前成长投入是否真正有价值

experience_chain:
  - 期待
  - 验证
  - 困惑
  - 不满

evidence_ids:
  - EV_003821
  - EV_003827
  - EV_003831

core_observation:
  玩家抱怨的重点并非单纯敌人强，而是成长投入没有形成预期中的相对优势。

interpretation:
  可能涉及成长反馈不足，或者敌人强度变化抵消了玩家对成长的感知。

boundary:
  仅凭该段实况不能确认游戏客观采用敌人等级同步。

why_valuable:
  可以支撑“为什么升级后玩家反而产生白刷感”的讨论。

external_fact_needed:
  - enemy_scaling_rule

confidence:
  HIGH

value_level:
  HIGH
```

---

## 5.3 Event Lite

中低价值事件不再使用旧“三行骨架”。

改为：

```yaml
event_id:

title:

topic:

change:

evidence_ids:

why_valuable:

value_level:
```

例如：

```yaml
title:
  第三次死亡后开始厌烦重复跑图

change:
  挑战欲 → 重复疲劳

evidence_ids:
  - EV_00431
  - EV_00439

why_valuable:
  可以作为失败惩罚开始反噬挑战乐趣的辅助证据。

value_level:
  MEDIUM
```

---

# 6. 第三层：Question

## 6.1 为什么需要 Question

你的写作更适合从：

```text
“这里为什么会这样？”
```

生长，而不是从：

```text
“这一部分应该写成长系统。”
```

生长。

所以系统应该专门存“值得继续追的问题”。

---

## 6.2 Question Schema

```yaml
question_id: Q_0018

question:
  为什么升级之后，玩家反而失去了成长感？

related_events:
  - EVT_0023
  - EVT_0031
  - EVT_0045

status:
  OPEN

strength:
  HIGH

possible_directions:
  - 成长反馈
  - 敌人强度
  - 数值可感知性
```

Question 不要求立即回答。

它是一种：

> 创作入口。

---

# 7. 第四层：Thread

## 7.1 定义

Thread 是多个 Event 围绕同一个矛盾、问题或者体验变化形成的创作线索。

它回答：

> 哪些散落的体验，其实可以写成一件事？

---

## 7.2 示例

```yaml
thread_id: THREAD_07

title:
  一张“废牌”如何让我重新理解整个资源系统

central_tension:
  初看像废牌
  vs
  理解机制后发现它承担资源循环功能

events:
  - EVT_0012
  - EVT_0027
  - EVT_0041
  - EVT_0063

turning_point:
  EVT_0027

start_state:
  玩家认为这张牌没有价值

end_state:
  玩家主动围绕其进行构筑

potential_thesis:
  游戏真正高明的地方不是让所有牌都强，而是让看似无用的牌也承担系统功能。

branch_material:
  - EVT_0019
  - EVT_0034

ending_direction:
  从一张卡牌的认知反转，回到整个系统如何减少“废牌”。
```

---

# 8. Tension：把“矛盾”升级为核心字段

现有系统主要记录：

```text
主题
```

例如：

```text
成长系统
卡牌系统
关卡设计
```

新版必须新增：

```text
tension
```

例如：

```text
明明升级
vs
却感觉没有变强
```

```text
初看是废牌
vs
理解系统以后变成核心
```

```text
Boss 很难
vs
真正消磨玩家的是重复跑图
```

原则：

> 主题负责分类，矛盾负责长文章。

每个 HIGH Event 和 Thread 都优先尝试提取 tension。

---

# 9. 第五层：Writing Packet

## 9.1 定义

Writing Packet 是真正开始创作时生成的临时工作包。

它不是完整大纲。

它应该保持：

* 短句；
* 模块；
* 可跳跃；
* 可增删；
* 不强制顺序。

目的是帮助作者启动和收束，而不是限制正文。

---

## 9.2 Writing Packet 示例

```text
写作方向：

“为什么升级以后反而觉得自己白练了？”
```

### 核心矛盾

```text
玩家投入成长资源
vs
没有感受到明显的相对优势
```

### 核心问题

```text
一个成长系统什么时候会让玩家感觉不到自己成长？
```

### 核心 Event

```text
EV23
第一次升级

EV39
发现敌人战斗压力并未下降

EV57
构筑成型之后重新获得成长感
```

### 体验轨迹

```text
期待
→
失望
→
怀疑
→
理解系统
→
重新评价
```

### 最有力 Evidence

系统直接显示原话，不让模型改写。

### 潜在判断

```text
成长系统的问题不一定是数值收益低，
也可能是收益缺乏即时可感知反馈。
```

### 支线

```text
敌人 scaling
刷资源效率
装备升级
```

### 支线兜回点

```text
所有支线最终必须回到：

“玩家有没有感觉自己因为投入资源而变强？”
```

### 开头入口

```text
A：
从玩家原话开始。

B：
从“RPG 升级本来应该开心”这个反常识切入。

C：
从自己前两个小时一直认为“刷得还不够”开始。
```

### 标题种子

```text
升级以后，我为什么反而觉得自己白练了？

RPG 最怕的不是成长慢，而是让你感觉不到成长

明明等级更高，我怎么反而越来越弱了？
```

### 结尾方向

```text
好的成长系统不只是让数值增加，
而是持续向玩家确认：
你刚才投入的时间没有白费。
```

### 待核事实

```text
enemy_scaling_rule
```

---

# 10. 新版正式流水线

## 第 0 段：导入链

执行者：

```text
程序
```

现有系统完全保留。

输入：

```text
TXT
```

输出：

```text
series
games
game_versions
sources
segments
```

现有：

* speaker；
* 行号；
* episode；
* version；
* import_guard；

全部保留。

---

# 11. 第 1 段：规则筛窗

继续使用：

```text
screen_windows.py
```

现有 8 类信号继续保留：

* 卡关；
* 吐槽；
* 惊喜；
* 发现；
* 对比；
* 抉择；
* 情绪爆发；
* 反常识。

未来新增第 9 类：

```text
认知变化
```

典型词：

```text
原来
我以为
怪不得
等等
所以说
我懂了
不是
我收回
刚才还
后来发现
难怪
```

目标：

> 高 Recall，不追求极端 Precision。

信号负责：

```text
定位
```

不负责：

```text
删除上下文
```

继续保留窗口扩展。

---

# 12. 第 2 段：粗判

继续保留现有：

```text
Qwen3-4B
+
DeepSeek-R1 争议复核
```

输出：

```text
KEEP
MAYBE
DROP
```

粗判唯一问题：

> 是否值得花强模型成本进一步阅读？

禁止粗判模型尝试：

* 写卡；
* 写深入结论；
* 做设计分析；
* 生成文章判断。

---

# 13. 第 3 段：Block 合并

新增一层：

```text
windows
↓
blocks
```

原因：

真实体验经常跨多个窗口。

例如：

```text
W12
第一次发现机制

W16
开始实验

W21
理解机制

W27
观点反转
```

程序根据：

* 时间距离；
* 主题词；
* 游戏实体；
* 机制名；
* 语义相似；
* 连续 episode；

优先合并成：

```text
BLOCK_07
```

强模型一次读取一个 Block。

目的：

* 减少重复阅读；
* 保留体验过程；
* 提高观点变化识别率。

---

# 14. 第 4 段：强模型精读

这是整条采矿线最核心、最值得花钱的阶段。

强模型输入：

```text
Block 原文

+
最近相关 Event

+
游戏基础上下文
```

强模型输出：

```text
Evidence 选择
Event Lite
Event Full
Question
Thread Signal
Tension
External Fact Need
```

禁止直接写完整 Card。

---

# 15. Thread Signal

精读时不要直接要求模型完整生成 Thread。

先记录：

```yaml
thread_signal:

  contradiction:
    玩家之前认为 X
    后来认为 Y

  relation_to_previous:
    contradicts:
    develops:
    confirms:

  possible_question:

  possible_role:
    setup
    turning_point
    payoff
    supporting
```

后续再由便宜模型完成聚合。

这样避免强模型在精读阶段承担过多组织任务。

---

# 16. 第 5 段：Event 去重、聚合与 Thread 建立

执行者：

```text
程序
+
embedding
+
便宜模型
```

任务：

* Event 去重；
* 相似 Event 合并；
* 建立关联；
* 找观点反转；
* 找因果链；
* 找长期体验变化；
* 生成 Question 聚类；
* 生成 Thread。

如果低成本模型判断不确定：

```text
标记 HUMAN / STRONG_REVIEW
```

而不是自动做复杂推理。

---

# 17. 第 6 段：素材矿库

正式采矿流程到这里结束。

一个游戏完成后首页显示：

```text
《游戏名》

Event：34

HIGH Event：9

强矛盾：6

Open Question：8

成熟 Thread：4

待核事实：3

推荐创作方向：3
```

不要默认显示：

```text
26 张素材卡
```

---

# 18. 联网核验改为按需触发

现有 web_facts 系统保留。

但原来的：

```text
粗判
↓
联网
↓
精读
```

改成：

```text
Event / Thread
↓
标记 external_fact_needed
↓
真正需要时联网
```

触发条件：

```text
Event = HIGH

或

进入 Writing Packet

或

被文章使用

或

人工主动要求核验
```

Fact 继续保存：

```text
web_facts/<游戏>.json
```

继续保留：

* facts / community 分区；
* claim 去重；
* verified_at；
* 易变事实当日重核；
* 官方 / 社区等级；
* 来源链接；
* 来源页逐字片段。

---

# 19. 创作阶段

当作者决定：

```text
“我要写这个游戏”
```

系统开始第二条流水线。

---

# 20. 第 7 段：Thread 推荐

系统根据：

* HIGH Event；
* tension 强度；
* Event 数量；
* 观点变化；
* 证据数量；
* Question 强度；
* 外部事实可验证程度；

推荐：

```text
3～6 条 Thread
```

例如：

```text
1.
升级系统为什么让人产生“白刷感”

2.
某张废牌如何让我理解整个资源系统

3.
真正让失败变烦的不是 Boss，而是重复流程
```

作者只需选择：

```text
我想写哪个。
```

---

# 21. 第 8 段：生成 Writing Packet

系统根据选中的 Thread：

```text
Thread
+
Event
+
Evidence
+
Fact
```

生成 Writing Packet。

Writing Packet 必须包含：

```text
核心矛盾

核心问题

体验轨迹

关键 Event

关键原话

潜在判断

支线

兜回点

标题种子

开头入口

结尾方向

待核事实
```

不生成完整文章。

不生成死板三级大纲。

---

# 22. 第 9 段：自由正文写作

作者按照自己的方式写。

允许：

* 跳着写；
* 先写中间；
* 先写结尾；
* 临时加支线；
* 换 Thread；
* 插入新的类比。

系统不强迫作者按照 Writing Packet 顺序。

---

# 23. OPEN_LOOPS：支线兜回账本

写作过程中，只要出现：

```text
[兜回?]
```

或者系统判断开启了明显支线，就加入：

```text
OPEN_LOOPS
```

例如：

| 支线           | 来源    | 应兜回到 | 状态     |
| ------------ | ----- | ---- | ------ |
| 敌人 scaling   | EVT23 | 成长反馈 | OPEN   |
| POE 类比       | 手动    | 构筑自由 | CLOSED |
| Roguelike 重开 | EVT51 | 长线动力 | OPEN   |

文章结束后系统只提醒：

```text
还有哪些坑没有填。
```

而不是直接重写文章。

---

# 24. 标题辅助

标题不要放在最后才从零生成。

Thread 成熟后提前生成：

```text
title_seeds
```

写到正文中段时：

```text
提醒作者挑选 2～3 个
```

最后只：

```text
选择
微调
```

不从零开始压缩整篇文章。

---

# 25. 开头辅助

开头不建议一开始就要求生成。

系统只准备：

```text
opening_entries
```

形式：

```text
原话入口

反常识入口

体验反转入口

具体场景入口
```

等正文主体已经形成后，再选择入口回填。

这符合现有创作习惯：先写中段或者尾部，再用完整视角补开头。你的痛点研究也明确指出，开头要求“先聚焦”与发散型起手天然冲突，因此后填更合适。

---

# 26. 第 10 段：收尾助手

这是系统应该重点自动化的部分。

自动完成：

### 文字检查

```text
错别字
标点
重复
病句
明显语义错误
```

### 逻辑检查

```text
观点突然跳跃
结论缺证据
前后冲突
因果倒置
```

### 闭环检查

```text
OPEN_LOOPS 是否清零
```

### 事实检查

```text
涉及外部事实的判断是否已有 Fact
Fact 是否过期
措辞是否超过证据强度
```

### 内容检查

```text
标题是否被正文接住
开头是否进入主题
结尾是否回到核心问题
```

### 发布工程

```text
封面
配图
图片缺失
返链
格式
发文清单
```

你的创作痛点中，收尾工程本身就是明显薄弱环节，适合全部外化成清单和工具，而不是依赖创作状态。

---

# 27. Card 的新定位

Card 保留。

但 Card 不再属于“采矿主流程”。

只有以下情况生成：

```text
文章需要引用

需要导出给其他模型

需要跨游戏比较

需要人工研究

旧系统兼容
```

流程：

```text
Event / Thread
↓
build_cards_from_events.py
↓
Card JSON
↓
craft_cards.py --from-json
```

Card Builder 使用：

```text
本地模型
或
低成本联网模型
```

强模型一般不参与。

---

# 28. 五维评分的处理

旧：

```text
玩家帮助
判断增量
具体性
独特性
写作价值
```

可以继续保留，用于 Card。

但不要让强模型在精读阶段完整打五维。

Event 阶段只需要：

```text
value_level:
HIGH / MEDIUM / LOW

confidence:
HIGH / MEDIUM / LOW
```

真正生成 Card 时再由便宜模型计算详细评分。

---

# 29. 人工验收策略

取消：

```text
所有 Card 全量验收
```

改成优先验：

```text
HIGH Event

HIGH Thread

低置信度 Event

外部事实冲突项

系统无法判断的异常项
```

MEDIUM：

```text
默认归档
真正使用时再审
```

LOW：

```text
仅留 Lite
```

目的：

> 避免产生越来越大的“验收债务”。

---

# 30. 缓存体系

至少建立：

```text
Window Cache
Block Cache
Event Cache
Thread Cache
Fact Cache
```

Event Cache 是最重要的。

Event hash 建议包含：

```text
source segments
prompt version
model version
```

如果：

```text
原始实况未变
Event Prompt 未变
```

就不重新花强模型成本。

即使：

```text
Card 格式变
Writing Packet 模板变
```

也不影响 Event。

---

# 31. 推荐目录结构

```text
project/

00_raw/
    transcript.jsonl

01_windows/
    windows.jsonl
    gate-state.json
    readlist.jsonl

02_blocks/
    blocks.jsonl

03_evidence/
    evidence.jsonl

04_events/
    events-full.jsonl
    events-lite.jsonl
    rejected.jsonl

05_questions/
    questions.jsonl

06_threads/
    threads.jsonl
    thread-signals.jsonl

07_facts/
    web_facts.json

08_writing/
    packets/
    open_loops/
    drafts/

09_cards/
    generated/
    approved/

10_reports/
    mining-summary.md
    writing-summary.md

cache/
```

---

# 32. 数据关系

核心关系：

```text
Evidence
↕
Event
↕
Question
↕
Thread
↕
Writing Packet
```

具体：

```text
Evidence ↔ Event
多对多

Event ↔ Question
多对多

Event ↔ Thread
多对多

Question ↔ Thread
多对多

Thread → Writing Packet
一对多

Event ↔ Fact
多对多

Event ↔ Card
多对多
```

这样同一个 Event：

```text
可以进入多篇文章
可以属于多个 Thread
可以支撑不同 Question
可以生成不同 Card
```

无需复制原始数据。

---

# 33. 模型岗位划分

| 岗位                       | 执行者             |
| ------------------------ | --------------- |
| TXT 导入                   | 程序              |
| speaker / 行号 / timestamp | 程序              |
| 规则召回                     | 程序              |
| 粗判                       | Qwen3-4B        |
| 粗判争议复核                   | DeepSeek-R1     |
| Block 合并初筛               | 程序 / embedding  |
| Event 提取                 | 强模型             |
| tension 提取               | 强模型             |
| Question 提取              | 强模型             |
| Thread Signal            | 强模型             |
| Event 去重                 | embedding / 小模型 |
| Thread 聚合                | 便宜模型            |
| Fact 核验                  | 联网模型            |
| Writing Packet           | 中低成本模型          |
| Card 扩写                  | 本地 / 低成本模型      |
| 五维评分                     | 便宜模型            |
| 原话校验                     | 程序              |
| speaker 填写               | 程序              |
| Fact 挂载                  | 程序              |
| OPEN_LOOPS 检查            | 程序 + 模型         |
| 错字逻辑审稿                   | 便宜模型            |
| HIGH 异常复核                | 强模型             |

---

# 34. 新旧流程对应

旧：

```text
导入
↓
筛窗
↓
粗判
↓
联网
↓
精读
↓
手写完整卡
↓
渲染
↓
全量人工验收
↓
写库
```

新版：

```text
【采矿线】

导入
↓
筛窗
↓
粗判
↓
Block
↓
强模型精读
↓
Evidence + Event
↓
Question
↓
Thread
↓
素材矿库
```

然后：

```text
【创作线】

选择游戏
↓
推荐 Thread
↓
选方向
↓
按需联网
↓
Writing Packet
↓
自由正文
↓
OPEN_LOOPS
↓
标题 / 开头辅助
↓
收尾助手
↓
发布
```

Card：

```text
按需生成
```

不再默认全量生产。

---

# 35. 当前工程改造优先级

## P0：必须先做

### 1. 修改精读输出

从：

```text
主题
原话
为什么值得
```

升级成：

```text
Event Lite / Full
Tension
Question
Thread Signal
```

### 2. 建立 Event 存储

新增：

```text
events-full.jsonl
events-lite.jsonl
```

### 3. 原话引用改成 segment_id

模型不再手写 quote。

### 4. 联网核验后移

只记录：

```text
external_fact_needed
```

### 5. 停止默认完整制卡

采矿流程到 Event / Thread 即结束。

---

# 36. P1：第二阶段

新增：

```text
Event 去重
Question 聚类
Thread 聚合
```

完成游戏级：

```text
“最值得写的 3～6 个方向”
```

---

# 37. P2：第三阶段

制作 Writing Packet。

重点字段：

```text
核心矛盾
核心问题
体验轨迹
Event
Evidence
支线
兜回点
开头入口
标题种子
结尾方向
待核事实
```

---

# 38. P3：第四阶段

建立：

```text
OPEN_LOOPS
```

和收尾助手：

```text
错别字
逻辑
事实
支线闭环
标题正文匹配
开头
结尾
发布检查
```

---

# 39. 暂时不要做的东西

短期不建议：

```text
自动生成完整文章

自动生成复杂大纲

让本地模型重新理解全部窗口

为了“知识图谱”提前做复杂图数据库

所有 Event 都联网

所有 Event 都生成 Card

所有 Card 都要求人工审批
```

这些东西很容易再次把项目拖进“系统建设成本大于创作收益”。

---

# 40. 第一版 MVP

建议第一版只验证：

```text
windows
↓
强模型
↓
Event
↓
Question
↓
Thread
```

选一个已经有旧卡结果的游戏做 A/B 测试。

例如：

```text
命运之手
```

比较：

旧方案：

```text
26 张完整卡
+
34 条骨架
```

新版：

```text
多少 Event？
多少 Question？
多少 Thread？
```

最后让作者回答：

```text
哪一种输出更容易让我想到“这篇到底写什么”？
```

而不是只比较：

```text
谁生成更多素材。
```

---

# 41. 推荐评测指标

## 采矿指标

```text
Event Recall
```

人工认为重要的体验，有多少被找到。

```text
Event Precision
```

HIGH Event 中真正值得保留的比例。

```text
Event Redundancy
```

重复事件比例。

---

## 创作指标

最重要：

```text
Thread → 文章采用率
```

其次：

```text
Event → 最终正文采用率
```

```text
Writing Packet → 启动正文时间
```

```text
每篇文章人工检索素材时间
```

```text
收尾耗时
```

---

## 成本指标

核心 KPI：

```text
Cost per Used Insight
```

即：

> 为获得一个最终真正进入文章的有效洞察，消耗多少强模型时间和额度。

这是以后模型路由、筛窗门槛、粗判规则和 Event 分级真正应该共同优化的目标。

---

# 42. 最终设计哲学

整套系统最终不是：

```text
游戏实况
↓
AI
↓
文章
```

也不是：

```text
游戏实况
↓
大量卡片
↓
人工自己重新整理
```

而是：

```text
                作者
     发散 / 联想 / 判断 / 正文
                 ↑
                 │
Evidence → Event → Question → Thread
                 │
                 ↓
         Writing Packet
                 │
                 ↓
        收束 / 检查 / 完成
                 │
                 ↓
                作者
```

一句话定义：

> 让 AI 和程序保存、组织并收束你的发散，而不是替代你的发散。

对于这个项目来说，“找到更多语料”只是第一步。

真正有价值的终点应该是：

> 当实况里出现一个值得写的瞬间时，它不会在几十个小时的录音里消失；当你真正开始写文章时，也不需要重新翻几小时实况、几十张素材卡和一堆零散笔记，才能重新想起当时为什么觉得这件事有意思。
