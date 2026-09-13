# HANDOFF.md — 新会话必读交接文档

> 写给完全没有上下文的新会话。第一件事：通读本文件，再读 `AGENTS.md`（仓库门规）和 `00_PROJECT_OVERVIEW.md`。读完再动手，**不要问用户"我们之前做到哪了"**。

## 一、我们在做什么

**项目**：游戏实况写作系统（本目录 `I:\AIstore\game_writing_system_plan_v1`）。

**目标**：用户有大量游戏实况 TXT（录播/直播文稿），要建一套系统把它们**建档 → 切分成台词段（Segment）→ 分类说话人 → 切集（Episode）→ 提炼素材卡 → 最终产出游戏评论文章**。

**⚡ 方向调整（2026-09-14，最新优先级最高）**：用户产出 V2  redesign 计划（已存 `17_V2_REDIRECT.md`，**先读它再谈素材卡**）。核心变化：素材卡不再是核心永久结构，改以 **Evidence → Event → Question → Thread → Writing Packet** 五层为创作主线；Card 降级为"按需生成的临时展示格式"；联网核验后移（只记 `external_fact_needed`，真正用时才核）；强模型只做理解不做包装；新增 OPEN_LOOPS 支线兜回账本和收尾助手。**路线已定案：不开新项目，就在本仓库做**（V2 全是增量结构，对 AGENTS.md 冻结契约零冲击，属 Level B 可扩展）；实现分支 **`v2/event-first`** 已从 dev 拉出并推送。详见下方"下一步计划 0"。

**用户画像（务必遵守沟通方式）**：
- 无编程基础，全程讲大白话，禁用 git/branch/PR 等术语（先给通俗解释再用）。
- 偏好"帮我把东西直接做好"，而非给步骤说明。
- 严格工程纪律派：改动前先给方案、逐轮确认；**不许自由发挥**。
- 同一问题连续失败 2 次 → 自动停手并写入 `REVIEW_REQUEST.md`，报告用户。

## 二、已完成的（按 14_MVP_TASKS 的 16 步链）

**第 1~3 步已完成并多轮测试验证：建档链 + 导入链 + Source/Segment。第 7 步铺量制卡的管线三件套已落地跑通。**

### Git / GitHub 备份体系（2026-09-12 新建，用户亲自主导）
- **本地 git**，**云端公开仓库**：https://github.com/QUEQUE0926/game-writing-system ，main 与 dev 双分支均已推送。
- **分支规矩（用户拍板）**：main = 稳定主线，**需用户显式批准才可合并/更新**；dev = 日常工作分支。流程：改代码 → dev 上 commit + push → verify 全 PASS → 用户批准 → 并进 main。
- **`.gitignore` 挡住数据**：`data/`、`backups/`、`exports/`、`logs/` 一律不进 git——**公开仓库里只有代码，用户语料绝不公开**。用户选的是"数据另想办法备份"（B 方案），未做，别擅自改成数据入库。
- **推送配置（本仓库级）**：代理 = `http://127.0.0.1:7890`（端口随代理客户端重启可能变）；推送带 `GIT_TERMINAL_PROMPT=0`。仓库级署名 user.name=game-writing / user.email=local@backup。
- **令牌坑**：用户 GitHub 令牌是 fine-grained PAT；诊断手法：`GET /repos/<owner>/<repo>/contents/` 返回 404 = 令牌无内容权限。

### 架构（全部已落地、verify 全 PASS）
- **环境隔离**：`data/<dev|test|prod>/` 三套物理隔离 SQLite。测试必须用 test 环境或临时目录（`GWS_RUNNING_TESTS=1` + `GWS_DATA_ROOT=$(mktemp -d)`），**禁止拿生产数据测试**。
- **Schema**：22 张表，当前 schema version = 4（004 加 `game_versions.sort_key` 展示排序）。
- **主拓扑**：`series → games → game_versions → sources → segments`，UUIDv7 稳定 id 外键。
- **状态机**：长期实体表有 status（active/archived/deprecated/trashed）；5 张纯关系表无 status，直接删 + audit_log。

### 入口（用户日常使用方式）
1. **拖放弹窗**：拖 txt 到 `drop-import-dev.bat` → tkinter 弹窗预填、边填边实时查库（绿=复用/红=冲突警告）→ 点导入弹确认预告 → 源文件**原地不动**，副本进 `data/<env>/inbox/drop-import/`。bat 必须指向**系统 Python**（`C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`）。
2. **prepare / auto-import**：inbox 扫描自动导入。
3. **CLI**（`scripts/gws.py`）：`init / info / create-* / import-txt / import-files / rename-*/ add-alias / find / list / export-html / set-version-order / auto-import`。
4. **查询档案.bat**：输入名字关键词 → 门牌 + 源文件完整路径 + 台词数。只读。

### 素材卡自动化三件套（2026-09-12 落地）+ 本会话大修
1. `scripts/screen_windows.py`——规则召回+窗口合成（8 类信号词、±20 句、双分制：总分≥3 入围、密度分排序）。产出每游戏+版本筛选工作台 + `windows-<日期>.jsonl`。
2. `scripts/coarse_gate.py`——本地双模型粗判（主判 qwen3:4b-instruct-2507 JSON schema 强制 + 复核 deepseek-r1 只接争议件），产出 `readlist-<日期>.jsonl` + 粗判工作台；判定缓存 `gate-state.json` 断点续跑。
3. `scripts/craft_cards.py`——精读产卡。程序锁：原话逐字锁（重试一次再不进 human_check）、同窗去重、证据位置程序带出。支持 `--from-json`。
- **2026-09-13 本会话大修（commit eaabbcd，别回退）**：发现 craft_cards 长期"双轨"——新版式渲染（按游戏+版本出文件、门牌行、五维打分分档、稳定卡号、跨版本挂链）只在 `--from-json`（手写卡）路径；LLM 自动路径还是旧单文件版式。已抽出共用 `render_outputs()`，两条路都走它；LLM 卡的 CARD_SCHEMA/PROMPT 补齐五维打分（help/concrete/delta/unique/writing 0~3）、联网策略四值、related；说话人标签改程序侧从原话命中句带出（模型无权填）。
- **本地模型岗位表（定案勿回退）**：qwen3-4B=主判官+产卡替身；deepseek-r1 7.6B=复核员；qwen3:1.7b/0.6b 判断岗否决；embedding 等第二个游戏产卡后复测。

### 制卡 A/B 两路（规矩，新会话必须知道）
- **A 路 = 本地小模型全自动产卡**：快（几分钟 81 张）、格式合格、**内容浅、无联网核验**。定位是"链路测试替身/格式预览"，**不是正式卡**。
- **B 路 = 会话 AI 手写+联网核验（正式路，05 文档定案）**：会话 AI 精读 readlist 窗口 → **两段式产卡**（先全量三行骨架、只精写中高价值卡）→ 该联网核验的按 09-13 联网规矩逐条核（事实核验/社区佐证分轨、三件套：结论含等级措辞+链接+来源页逐字片段）→ 核验进 `web_facts` 档案自动挂载（易变条目当日重核）→ `craft_cards.py --from-json` 渲染（同一套程序锁/版式）→ 用户验收 → `import_cards.py --apply` 写库。
- **用户问"制卡"默认走 B 路**；跑 A 路只为测试流水线或给用户看格式效果。将来用户给联网强模型 API key，A 路升级，此规矩再议。

### 报告只留最新（2026-09-13 落地，commit ee6647d）
- `src/gws/report_prune.py`：产线脚本写完自动清理同模式旧日期报告（只动 .md/.json 报告，**绝不碰 jsonl/gate-state.json**——断点续跑和跨日流程靠它们）。
- 已手工清过一轮旧报告。05 文档「报告版式规矩」节有记录。

### 核验档案与自动挂载（2026-09-13 用户拍板落地）
- `src/gws/web_facts.py` + `data/<env>/web_facts/<游戏>.json`：核过的事实存档案（三件套齐全），
  `craft_cards.py --from-json` 渲染前按 triggers **自动挂载** fact_check；同 claim 去重。
- **易变红线**：volatile 条目（价格/补丁/销量）verified_at 不是当日 → 拒挂并打印当日重核清单，
  重核后更新日期再渲染。社区佐证不自动挂（编辑判断，人工挑）。
- 卡量收敛线（构建器自检，报警不硬拦）：每窗>2 张、全批>40 张。
- 灰烬之国档案已灌：facts 24（volatile 5）+ community 16。**命运之手档案已灌（09-13）**：facts 8
  （volatile 2：EA价格、v0.1补丁，均当日重核）+ community 1（小黑盒0命中停用登记）；
  亮点：官方补丁逐字证实「神社/少女遭遇=Shrine/Maiden、史诗=Platinum、祈求长寿=Maiden longer life」，
  与实况口述逐条吻合；24 官方成就全量逐字（冒险名/英雄卡/老练英雄=50级/选牌大师=250次洗牌）。单测 7 条 `tests/unit/test_web_facts.py`。
- 下次 B 路产卡流程变化：卡 JSON 不内嵌核验条目（渲染时自动挂），只有档案够不着的才手工挂。
- **两段式产卡（同日落地，用户拍板方案一）**：卡源 JSON 每窗口分 `cards`（完整卡）+ `skeletons`
  （三行骨架：主题/原话/为什么值得，逐字锁照走）；骨架渲染成单独的《游戏》素材卡骨架清单
  （按游戏+版本），不进卡候选、不写库，当目录+素材储备；低骨架不精写。单测 3 条
  `tests/unit/test_craft_skeleton.py`。下次产卡：先骨架全量 → 只精写中高 → 验收只看草稿。

### 导入防线①②（2026-09-13 用户拍板落地，commit 24c9f24）
- `src/gws/import_guard.py`：**① 版本名相似提醒**（新建版本时同游戏下已有相似名——互相包含或相似度≥0.5 且差异不全是数字，「8月更新」vs「8跟新」抓得住，「V1.0」vs「V2.0」不误报）；**② 同内容跨版本提醒**（文件 sha 与本游戏另一版本已有实况完全相同）。
- 三处接线：拖放弹窗预告 / CLI 输出 / auto_import 结果。**只提醒不拦截**。
- 单元测试 `tests/unit/test_import_guard.py`；04 文档「导入防线」节有记录。

### 写库器
- `scripts/import_cards.py`（2026-09-13）：`cards-state-<日期>.json` → material_cards + material_card_evidence + audit_log。默认 dry-run，`--apply` 落库。字段映射固定（detail→observation、feeling→experience、analysis→interpretation、judge_reason→judgement、concrete→evidence_strength、writing→writing_value、help→author_interest、unique→reuse_value）；证据=原话去空白后在窗口行区间 segments 逐字命中，命中 0 条拒绝入库；同 episode+同 quote 幂等跳过。

## 三、当前状态（2026-09-14 收工：V2 方向已定案、实现分支已建，旧线卡在等用户验收 + 代理未恢复）

**旧线**：没有卡点，等用户验收两批 B 路卡（或指出要改的卡）。
**新线（V2）**：方向讨论完毕、分支已建好，**还没写一行 V2 代码**。P0 第一刀（events/questions/threads 迁移）未动。

**Git 状态（重要，别搞乱）**：
- 当前分支 = **`v2/event-first`**（从 dev 拉出，已推送远端）。V2 的所有代码改动都在这条分支上做。
- **本地 dev 领先 `origin/dev` 2 个提交**（`e85d3bb`、`0673bbd`——后者是 REVIEW_REQUEST：Clash 界面活着但代理核心无监听，坑32）。这 2 个提交已随 `v2/event-first` 推送上云，但 `origin/dev` 本身还没有。代理恢复后需补推 dev，否则别的机器拉 dev 会缺这 2 个提交。
- `17_V2_REDIRECT.md`（V2 计划全文）本次已写入仓库并随分支提交——原稿一度只存在于 ZCode 粘贴临时目录（会被清理），已抢救。

- **dev 库现有 4 个源**：《灰烬之国》正式版 666 句 + 8月更新 515 句、《命运之手》2325 句、《零秒：时光的归途》1481 句（旧 29 源数据 09-12 已清，这四个都是之后重新导入的）。
- **A 路 81 张机器卡已按用户拍板弃掉**（"走个B路"）。卡片原始数据在 `data/dev/exports/cards/cards-state-《命运之手》-20260913.json`（按游戏分文件新格式，见坑46）；**灰烬 52 卡 state 因是修复前产出、只有 tmp 备份：`data/dev/tmp/cards-state-20260913.backup-灰烬52卡.json`**。
- **B 路·灰烬之国 52 卡已产出**（会话 AI 精读 25 窗手写 → 联网核验 → `--from-json` 渲染，逐字锁 0 拦截）：
  - 《灰烬之国》素材卡草稿（正式版）26 卡（高2/中20/低4）+ human_check 3 条
  - 《灰烬之国》素材卡草稿（8月更新）26 卡（高2/中20/低4）+ human_check 3-4 条
  - 卡源 JSON `data/dev/tmp/my_cards.json`（构建器 `data/dev/tmp/build_b_cards.py`，内含 quote 逐字自检，可复跑）
- **B 路·命运之手 26 卡 + 34 骨架（09-13 带计时重跑版）**：
  - 粗判 28 窗（KEEP16+MAYBE12，缓存命中瞬时完成）→ 精读复读 244s → 手写 462s（26 精写：高15/中11 + 34 骨架：中14/低20）→ 渲染 0.0s（自动挂载 7 条，逐字锁 0 拦截）
  - 产出：`data/dev/exports/cards/《命运之手》素材卡草稿（default）-20260913.md` + `《命运之手》素材卡骨架清单（default）-20260913.md`
  - 卡源 JSON `data/dev/tmp/hof_cards_grouped.json`（构建器 `data/dev/tmp/build_hof_cards.py`，从 `read_windows_ms.txt` 重建窗口文本做逐字锁）
  - **计时记录**：`data/dev/logs/timing-命运之手-20260913.jsonl`
  - **注意**：原 44 骨架中 10 条因与精写卡重复或窗口匹配问题未纳入，实际 34 条。
- **联网核验（2026-09-13 当日全重核）·灰烬之国**：商店页 API（名/开发商发行商/EA日期/价¥68当日无折扣）；新闻 API（最新补丁仍 V0.6.11b 8月25日，此后无新补丁）；**官方成就页三枚彩蛋**：「植物大战僵尸」=塞弗林的水壶、「小心！别照镜子！」=美杜莎之眼、「一个都别想跑！」=打地鼠5000分、「斩尽荆棘」=击败塞弗琳；Gamemag.ru 报道 V0.6.10「Isdra」重做。社区佐证沿用小黑盒 665862 话题缓存（09-08~09-12 帖）。转人工（human_check）：EA期约12个月无出处、难度与角色绑定无官方说明、修改器合规性存疑、德鲁伊事件bug无公告、炮手被削无信号。
- **联网核验·命运之手**：商店 API（《命运之手：人各有命》Hand of Fate: Hordes，appid 3075410，Spitfire Interactive 开发/Spicy Koala 发行，2026-07-22 EA ¥48 当日无折扣）；v0.1『Loading and Loadout』补丁公告（2026-09-09，自动存档/loadout 系统/神社少女遭遇令牌分支，逐字片段齐）；官方成就页 24 条全量逐字；小黑盒 0 命中已停链路。
- **计时功能（2026-09-13 落地，commit 4cda26c）**：`src/gws/pipeline_timing.py` + `scripts/timing.py`，三个产线脚本（筛窗/粗判/产卡）自动记录各阶段耗时。命运之手重跑实测：筛窗 0.1s → 粗判 0.0s（缓存）→ 核验 0.0s（档案复用）→ 精读 244s → 手写 462s → 渲染 0.0s，合计约 706s（11.8 分钟）。
- **零秒：时光的归途**：已筛窗，**未粗判未制卡**。
- **最新 commit**：`4cda26c`（计时功能：pipeline_timing.py + timing.py + 三脚本接入 + 5 单测，verify 七步全 PASS 已推送）。

## 四、下一步计划（主线）

0. **V2 实现（2026-09-14 新主线，按 17_V2_REDIRECT.md 的 P0→P3 走，分支 `v2/event-first`）**：
   - **P0 第一刀**：新增迁移建 events / event_evidence（或等价关系表）/ questions / threads 几张**纯增量新表**（老卡表一个字段都不动，AGENTS.md 冻结项全不碰）→ 过 verify 七步。
   - 随后按 17 文档 P0 清单：精读输出从"主题/原话/为什么值得"升级为 Event Lite/Full + Tension + Question + Thread Signal；原话引用改 segment_id（模型只选 segment，程序取原话）；联网核验后移（只记 external_fact_needed）；采矿流程到 Event/Thread 即停，停止默认完整制卡。
   - **MVP 验证**：拿《命运之手》做 A/B（旧 26 卡+34 骨架 vs 新 Event/Question/Thread），判据是"哪种输出更容易让我想到这篇写什么"，不是比谁卡多。
   - 注意：V2 落地期间旧 B 路卡流程**原样保留**（A/B 需要两轨并存）；旧线验收（本条 1）与新线开发可并行，别互相阻塞。
1. **用户验收两批 B 路卡（灰烬 52 + 命运之手 26）+ 回填 human_check**（逐卡勾 采用/删除，改提交状态；命运之手 human_check 4 条：前作信息、等级30/32、CE合规×2）。验收通过 → 改名归档（05 流程）→ `import_cards.py --apply` 写库：命运之手用 exports 下的 `cards-state-《命运之手》-20260913.json`，灰烬用 `--file data/dev/tmp/cards-state-20260913.backup-灰烬52卡.json`（坑46：修复前的旧批次只剩这份备份）。
2. **零秒铺量**：coarse_gate --game 零秒 → B 路两段式产卡（流程同命运之手：粗判→精读→骨架全量+精写中高→建/复用 web_facts 档案→渲染→验收）。
3. **跨游戏关联（方案已定案写入 05，待实现）**：①玩家明说他游→当场画线（只关联本地库游戏；灰烬的「植物大战僵尸」提及卡已登记，待该游戏入库补线）；②内容相似 embedding 复测（第二个游戏产卡后）；③联网联想提前到素材卡阶段。落地顺序：验收写库 → 新游戏产卡（带信号1）→ embedding 复测 → 联网联想。
4. **体检命令③（用户提过，未做）**：扫全库空壳版本/近似版本/重复内容出体检报告。要做先出方案。
5. **规则权重校准（待数据）**：8 类信号词权重手拍，等人工勾选积累真卡后回归。
6. **联网模型可选升级**：用户给 API key（Kimi/GLM 等）后 craft_cards 换强模型。

**之后的路线**：第 8 步打标签/建关联 → 第 10 步后建写作项目 → claims（必须绑素材卡）→ 角度 → 主题（**必须用户拍板，是人工关卡**）→ 提纲 → 文章。再往后才是灵感卡（第 16 步）。

**已获用户授权的决策方式（重要）**：琐碎判断（如"第二发言人是谁""test 文件跳过"）**AI 直接定、直接干**，依据写进 audit_log，报表里告知结论；**不要逐项请用户拍板**。方案级的事（改流程、改分档规则）仍需先出方案确认。

**本地 Ollama 岗位**：粗判门控常驻（4B 主判 + r1 复议）。必须 JSON schema 强制格式 + 固定 seed（seed=42），能用规则的绝不请模型，能本地的不上联网。

## 五、踩过的坑（绝对不要再踩）

1. **测试"报红"先分清脚本错还是代码错**：三轮组合测试里所有"失败"全是测试脚本自身错。代码至今零冤案。**先复核测试用例再改代码。**
2. **便携 Python 3.13.12 无 tkinter** → 弹窗必须用系统 Python 3.13.15（`C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`）。
3. **`scripts/gws.py` 会遮蔽 `gws` 包名** → 测试里 import drop_dialog 用 `importlib.util.spec_from_file_location` 按路径加载。
4. **中文 txt 编码探测必须 strict**：`errors="ignore"` 永不抛异常不能用来试编码。顺序 utf-8 → gbk → gb18030，先处理 BOM。
5. **CLI `--env` 默认值必须 `os.environ.get("GWS_ENV", "dev")`**，别改回写死。
6. **executescript 隐式 COMMIT** → 迁移显式 BEGIN/COMMIT。
7. **SQLite NULL ≠ NULL** → UNIQUE 挡不住独立游戏同名，003 partial unique index 封，别删。
8. **purge 级联单环 SQL**：`WHERE col IN (同表子查询)` 永空，len==1 直接 `WHERE col=?`。
9. **枚举值唯一注册表在 AGENTS.md**：status/speaker/content_type/ref_type/source_type/tags.category/asset_type/consumer_type，代码里禁造同义词。
10. **结构改动唯一合法路径**：新编号迁移文件 → 过 verify。禁止 rename 表/列、复用 id、删列。`tests/integration/test_schema_contract.py` 把 22 表列名钉死。
11. **不要重跑已完成的上游阶段**；改代码后必跑 `PYTHONPATH=src python scripts/verify.py`（七步门禁），全 PASS 才算完。
12. **GitHub 推送 403** = 令牌缺 Contents 权限或代理端口变，先查这两样。连续失败 2 次停手写 REVIEW_REQUEST.md。
13. **REVIEW_REQUEST.md 是活文档**：新阻塞追加新段，别删旧记录。
14. **清空数据库 = 逐表 DELETE 业务数据，`schema_migrations` 绝对不能清**（清了库"失忆"重放迁移会报错）。修复=把缺的 (version, name) 补回。
15. **本环境删除可能被 genie-trash 拦截**（I 盘无回收站，fail-closed）→ 优先逐表 DELETE 或先 cp 备份。（注：2026-09-13 实测 exports 下 rm 正常，未触发，但别赌。）
16. **写 Windows bat 用 Write 工具**，shell printf 会吃掉转义。
17. **拷贝 WAL 模式的 SQLite 用 `sqlite3` 的 `src.backup(dst)`**，别直接 cp app.db。
18. **转写工具的"发言人1/2"只当线索**：按文件级映射处理，误归属一条 UPDATE 翻转。
19. **ASR 同音变体**：游戏名被转错靠 game_aliases 花名册，发现变体补别名，别改代码。
20. **断行粒度跨源差异巨大**：长度信号只能做"文件内部相对值"（如每集 p90），禁止绝对阈值。
21. **报告呈现规矩（用户否决过的别再提）**：① 每游戏一份工作台；② 分档按每游戏内部相对分；③ 仓库根 `exports/` 不碰；④ 报告只显示命中句引文。
22. **created_at 只有秒级精度** → 按时间兜底排序必须再补 `rowid`。
23. **make_episodes 幂等跳过是源级**；`--source` 前缀匹配会撞同批 UUIDv7 前缀，精确指定用完整 id。
24. **classify_speakers.py / make_episodes.py 默认试跑不落库，必须加 `--apply`**。screen_windows 报"0 游戏 0 窗口"，第一嫌疑就是分类没落库。
25. **qwen3 系列默认思考模式**：请求里 `"think": false` 或 JSON schema（`"format": {...}`），否则烧光 num_predict 输出空串。
26. **本地模型岗位已定勿回退**（见上）；自由文本格式 r1 解析失败——结构化输出必须 JSON schema 铐住；schema 的 maxItems 不执行，数量上限代码兜。
27. **screen_windows 双分制别改回**：总分只做入围门槛（≥3），排序用密度分（总分与窗口长度相关 r=0.68）。
28. **窗口匹配键必须含 source_id**：同版本多源时集名+行号会撞。
29. **原话逐字锁对谁都生效**（含 --from-json），不重试成功就进 human_check，绝不静默入库。
30. **human_check 每轮全量重写**，登记两类（逐字锁失败 + 各卡"待人工"项）；`if human_check:` 才写文件会留旧账（踩过）。
31. **大段 Edit 后必须 `ast.parse` + grep 检查**（出现过替换引入乱码/弯引号破语法）。
32. **git push 连接失败**：先重试一次；再失败 netstat 查代理端口，连续 2 次停手写 REVIEW_REQUEST。
33. **联网规矩（09-13 大修订）**：事实核验与社区佐证分轨，等级措辞冻结在 05「联网规矩」节，每条强制三件套。小黑盒必须走社区 id→话题流（灰烬之国 topic_id=665862 已实测，匿名搜索不可用），查不到停手转 human_check。知乎专栏 403 不硬闯。**Steam 商店页/新闻 API 走 urllib + 空 ProxyHandler + verify=False，不走代理**（7890 对 steam 连不上）。
34. **管线脚本不支持 `--help`**（传了会真跑，craft_cards 会真调 LLM 烧时间）。看用法读脚本头部 docstring。
35. **app.db 可能被无名系统进程占用删不掉**（WinError 32）→ 清库用逐表 DELETE，别硬删文件。
36. **重切集会移动窗口锚点**：line_start 全变，cards JSON 的窗口键失效；解法=按"同源且全部 quote 逐字命中"重映射，quote 是锚不会失效。
37. **`data/` 不进 git**：只改卡/报告时 commit 会是 "nothing to commit"，正常。
38. **卡数据标点规矩**：web_log/联网字段别自带"待人工："前缀（渲染时程序自动剥离）；卡内标点用直角引号『』；quote 必须与转录逐字一致（含错别字），送渲染前 norm+find 自查。
39. **segments 表的行区间列是 `line_start`/`line_end`**（不是 line_number）。
40. **小黑盒链路依赖**：跑 xhh 先 `pip install pyyaml`；"curl_cffi 未安装退回 httpx"警告属正常。
41. **craft_cards 双轨教训（09-13 踩过）**：改产线脚本时确认两条入口（LLM 主路径 / --from-json）都走同一渲染，别只改一边。（已修，修时见 commit eaabbcd）
42. **report_prune 第一版 bug 教训**：fnmatch 通配符模式**不能**用 `re.escape` 整个转义（会把 `*` 转死），要用 fnmatch 匹配+正则只提取日期段。（已修，修时见 commit ee6647d）
43. **import_guard 阈值教训**：difflib 相似度阈值 0.6 拦不住「8月更新/8跟新」（实际 0.571），定 0.5；差异全数字（V1→V2）排除以免误报正常版本递进。
44. **全库跑 screen_windows 会影响所有游戏**：它会重建全部已分类源的窗口并清理旧筛选报告；只想跑一个游戏加 `--game <名>`。
45. **web_facts 档案是纯 JSON 不是 Python（09-13 踩过）**：多行结论不能写相邻字符串隐式拼接（Python 习惯带进了 .json，第 10 行就炸）→ 档案读取失败、自动挂载整批跳过（有容错只告警，26 张卡全裸渲染完才发现）。写完档案必须 `json.load` 验证后再跑渲染。
46. **cards-state-<日期>.json 同日期跨游戏互相覆盖**（09-13 踩过）：文件名只有日期没有游戏名，第二个游戏同日渲染直接覆盖第一个。
  **已修复（同日）**：craft_cards 改为按游戏各写一份 `cards-state-《游戏名》-<日期>.json`（整轮空跑才退回旧式单文件）；import_cards 的"取最新"改用修改时间排序（中文名排序≠时间），多份并存时打印提醒可用 --file 指定；report_prune 新旧模式都登记。三个单测同步更新，verify 七步全 PASS。
  **遗留**：09-13 当天已被覆盖的灰烬 52 卡 state 仍只有 tmp 备份一份（见下条），写库前照旧恢复。
47. **dump 转存文件与 readlist jsonl 可能不同步**（09-13 踩过）：逐字锁只认 readlist jsonl（如 E13 行1626 dump 是"通往通往"、jsonl 是"通往"）；构建器自检必须对着 jsonl 跑，别对着人读用的 txt 转存抄原话。
48. **unittest 直接 discover 找不到 gws 包**：必须 `PYTHONPATH=src`（verify.py 会自动带，手工跑单测别忘）。
50. **--from-json 卡源 JSON 格式（09-13 重跑踩过）**：craft_cards 期望顶层是 `list`（不是 `{"items": [...]}`），每项含 `episode_title`/`window_line_start`（窗口起始行，不是 quote 所在行）/`cards`/`skeletons`；卡字段名是 `subject/detail/feeling/analysis`（不是五段式 observation 等），五维分数 `help/concrete/delta/unique/writing` 必须展平到顶层（不是 `scores` 字典），`tags`/`usage`→`use`。构建器必须先按窗口分组再送渲染。
51. **精读转存 txt 与 readlist jsonl 的 quote 差异（09-13 重跑踩过）**：重跑时 readlist jsonl 已被清理，只有 `read_windows_ms.txt`；逐字锁必须对着**实际送渲染的窗口数据源**重建（从 txt 按 `===== 窗口标题 =====` 解析），不能假设 jsonl 还在。E21:2673 的 quote 跨了两行（2673+2679），单行 quote 才能逐字命中。
52. **方向性文档必须当场落库，别留在粘贴临时目录（09-14 踩过）**：V2 redesign 全文最初只存在于 ZCode 的 `paste-attachments` 临时文件里，那目录会被清理。用户拍板的大方向文档，收到立刻写进仓库并 commit，别等"改天整理"。
53. **从本地 dev 拉分支会把 dev 未推送的提交一起带走（09-14）**：本地 dev 领先 origin/dev 2 个提交时拉出的 `v2/event-first` 包含了它们；dev 本身仍未推送。跨机器/跨会话对账时记住：origin/dev 缺 `e85d3bb`、`0673bbd` 两个提交，代理恢复后补推。
54. **V2 路线红线（09-14 用户已拍板，别重开讨论）**：不开新项目、不推翻 AGENTS.md 契约；V2 新结构（Event/Question/Thread 等）一律走**新增迁移**，老卡表与枚举一个不动；旧卡流程在 A/B 完成前不得删除或改死。

## 六、验证方式速查

```bash
# 全量门禁（必跑）
cd I:\AIstore\game_writing_system_plan_v1
PYTHONPATH=src "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" scripts/verify.py

# 隔离临时库演练（不碰 dev/test/prod）
GWS_RUNNING_TESTS=1 GWS_DATA_ROOT=$(mktemp -d) PYTHONPATH=src <python> scripts/gws.py ...

# CLI 用法
python scripts/gws.py find 名字     # 先看门牌再干活
python scripts/gws.py list
GWS_ENV=test python scripts/gws.py ...   # 环境变量优先生效
```

**每日工作日志**：`.workbuddy/memory/`（2026-09-11、09-12、09-13 有细节）。工程纪律见 `02_ENGINEERING_RULES.md`，数据模型见 `03_DATA_MODEL.md`，素材卡系统见 `05_MATERIAL_CARD_SYSTEM.md`，导入链见 `04_SOURCE_PIPELINE.md`，AI 门规见 `AGENTS.md`。

**本仓库 git 常用命令**（先 `git status` 确认在 dev 分支再操作）：
```bash
GIT_TERMINAL_PROMPT=0 git push          # 推当前分支（代理已配）
git add -A && git commit -m "说明"       # 存档点（在 dev 上打）
# main 只在用户批准后合并：git checkout main && git merge dev && git push && git checkout dev
```
