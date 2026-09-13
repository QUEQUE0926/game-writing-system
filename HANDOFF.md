# HANDOFF.md — 新会话必读交接文档

> 写给完全没有上下文的新会话。第一件事：通读本文件，再读 `AGENTS.md`（仓库门规）和 `00_PROJECT_OVERVIEW.md`。读完再动手，**不要问用户"我们之前做到哪了"**。

## 一、我们在做什么

**项目**：游戏实况写作系统（本目录 `I:\AIstore\game_writing_system_plan_v1`）。

**目标**：用户有大量游戏实况 TXT（录播/直播文稿），要建一套系统把它们**建档 → 切分成台词段（Segment）→ 分类说话人 → 切集（Episode）→ 提炼素材卡 → 最终产出游戏评论文章**。

**用户画像（务必遵守沟通方式）**：
- 无编程基础，全程讲大白话，禁用 git/branch/PR 等术语（先给通俗解释再用）。
- 偏好"帮我把东西直接做好"，而非给步骤说明。
- 严格工程纪律派：改动前先给方案、逐轮确认；**不许自由发挥**。
- 同一问题连续失败 2 次 → 自动停手并写入 `REVIEW_REQUEST.md`，报告用户。

## 二、已完成的（按 14_MVP_TASKS 的 16 步链）

**第 1~3 步已完成并多轮测试验证：建档链 + 导入链 + Source/Segment。**

### Git / GitHub 备份体系（2026-09-12 新建，用户亲自主导）
- **本地 git 已 init**，首个存档点 `8914223`（52 文件，仅代码/文档/测试）。
- **云端公开仓库**：https://github.com/QUEQUE0926/game-writing-system ，main 与 dev 双分支均已推送，本地/云端四处同步。
- **分支规矩（用户拍板）**：main = 稳定主线，**需用户显式批准才可合并/更新**；dev = 日常工作分支。流程：改代码 → dev 上 commit + push → verify 全 PASS → 用户批准 → 并进 main。
- **`.gitignore` 挡住数据**：`data/`、`backups/`、`exports/`、`logs/`、`__pycache__/`、`*.pyc`、`.workbuddy/` 一律不进 git——**公开仓库里只有代码，用户语料绝不公开**。用户选的是"数据另想办法备份"（B 方案），未做，别擅自改成数据入库。
- **推送配置（本仓库级）**：代理 `http.proxy`/`https.proxy` = `http://127.0.0.1:7890`（端口随代理客户端重启可能变）；推送带 `GIT_TERMINAL_PROMPT=0`。仓库级署名 user.name=game-writing / user.email=local@backup。
- **令牌坑**：用户 GitHub 令牌是 fine-grained PAT，能建仓库但默认无 Contents 权限 → push 403。已让用户在网页补 `Contents: Read and write` 解决。诊断手法：`GET /repos/<owner>/<repo>/contents/` 返回 404 = 令牌无内容权限。

### 架构（全部已落地、verify 全 PASS，约 41+ 测试）
- **环境隔离**：`data/<dev|test|prod>/` 三套物理隔离 SQLite，各含 `app.db、raw/、inbox/、exports/、backups/、tmp/`。测试必须用 test 环境或临时目录（`GWS_RUNNING_TESTS=1` + `GWS_DATA_ROOT=$(mktemp -d)`），**禁止拿生产数据测试**。
- **Schema**：22 张表。001 建 21 表 + 002 加 `game_aliases`（别名全库唯一）+ 003 加固（games 两个 partial unique index 封独立游戏同名 NULL 漏洞、episode_segments 加 position 列）+ **004 加 `game_versions.sort_key`**（手动版本序号，可空；NULL 排后按 created_at+rowid 兜底；仅影响展示排序）。当前 schema version = 4。
  改序号用 `python scripts/gws.py set-version-order <版本名或id> <数字|clear>`（多命中报错不猜，写 audit_log）。dev 已标：灰烬之国 正式版=1、8月更新=2。
- **主拓扑**：`series → games → game_versions → sources → segments`，全部靠 **UUIDv7 稳定 id** 外键关联，name 只在导入入口解析一次用。下游还有 episodes / material_cards / claims / articles 等已建表。
- **状态机**：长期实体表有 status（active/archived/deprecated/trashed，trashed 是终点且拒新引用）；5 张纯关系表（episode_segments、material_card_evidence、asset_tags、claim_evidence、project_assets）**无 status**，直接删 + audit_log。

### 入口（用户日常使用方式）
1. **拖放弹窗**：拖 txt 到 `drop-import-dev.bat` / `drop-import-prod.bat` → tkinter 弹窗预填（系列/游戏/版本），**边填边实时查库**（绿色=复用/新建明细，红色=冲突/重复警告），点导入再弹确认框 → 源文件**原地不动**，复制副本到 `data/<env>/inbox/drop-import/` → 导入成功自动删副本，失败保留副本排查。注意：bat 必须指向**系统 Python**（`C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`），便携版 3.13.12 无 tkinter。
2. **prepare / auto-import**：inbox 扫描自动导入。
3. **CLI**（`scripts/gws.py`）：`init / info / create-* / import-txt / import-files / rename-*/ add-alias / find / list / export-html`。`find <名字>` 模糊查三类档案并排显示门牌（系列→游戏→版本）+ id，多命中绝不猜。
4. **查询档案.bat**（2026-09-12 新增，双击运行）：输入名字关键词 → 显示门牌 + **源文件完整本地路径** + 台词数 + 原文是否还在（丢失会标注）。只读。脚本在 `scripts/find_tool.py`，默认查 dev 环境。

### 关键业务规则
- 命名规范：`系列 - 游戏 - 版本.txt`（无系列则 `游戏 - 版本.txt`），默认系列=游戏名，`#N` 为同版本多实况序号。
- 匹配 `_resolve_target`（src/gws/auto_import.py）：显式系列 → 严格系列内匹配；默认系列 → 先找同名系列，否则全局主名→别名，**唯一命中才复用，多命中报错不猜，零命中新建**。
- 去重：同版本 + 相同 sha256 → 跳过。
- rename 自动留旧名为别名；purge：级联软删 owned-children → 备份 → confirm 后物理删除。
- 导入只接受 `.txt`（docx 支持已按用户要求撤销）。
- 只读原文归档：`data/<env>/raw/<sha前2位>/<sha>.txt`，永不覆盖。

## 三、当前状态（2026-09-13 更新：33 卡按联网新规矩重核完毕，写库器落地，等用户验收）

**没有卡点。等用户验收《灰烬之国》33 张素材卡（正式版 18 + 8月更新 15）+ 回填 human_check（各 14 条待填）。验收通过并回填后，`scripts/import_cards.py --apply` 一键写库，然后铺量其余游戏。**

- **重要：dev 库 2026-09-12 被用户清空过一次**（原文副本 raw/ 也删了，因为哈希文件名对不上号），随后用户重新导入了《灰烬之国》两份实况。**当前 dev 库只有这 2 个源**：正式版 666 句 + 8月更新 515 句，共 1,181 句、25 集（正式版 14 + 8月更新 11）。旧 29 源 27,557 句数据没了，其他游戏的源要重新导入。
- **本会话（2026-09-13）落地的大事（均已 verify 全 PASS + push dev）**：
  1. **联网规矩大修订**（05 文档「联网规矩」节 + 坑34 修订）：事实核验与社区佐证/扫描**分轨**。事实核验查官方一手源（商店页→公告/patch notes→厂商官网→原始访谈→论文/文档→可靠媒体），按 5 类核验对象触发、不受价值档限制；社区平台（14 个）只作佐证，结论带等级措辞（强证实/弱证实/反证/无信号/无法验证）；弱证实不能单独作结论、反证转 human_check 不许 AI 自改。每条核验强制三件套：结论（含等级措辞）+ 具体链接 + 来源页逐字原文片段。
  2. **卡数据重建**：`data/dev/tmp/my_cards.json` 联网字段拆为结构化 `fact_check`/`community_scan`（旧 `web_check`/`ai_web` 自由文本已退役；重建脚本 `data/dev/tmp/rebuild_cards_web.py`；旧卡备份 `my_cards.backup-20260913.json`）。craft_cards 渲染分「核对（事实核验）」「社区参照（非事实依据）」两栏，存疑/无信号/无法验证自动进 human_check。
  3. **33 卡全部重核**：新核出开发方 MyACG Studio（发行方含 NPC Entertainment）、8月三连补丁（V0.6.11 8/14 调饰品掉率、V0.6.11a 8/16 修bug、V0.6.11b 8/26）、官方成就页证实『塞弗林的水壶』、知乎证实钓鱼小游戏；『莉薇特』按规矩降级为社区佐证待官方源确认；B站小红流派合集补上具体视频链接 BV11EqwBBE7X。小黑盒链路实测通（topic_id=665862，20 帖存 `data/dev/tmp/xhh_665862_feed.json`）。
  4. **素材卡写库器 `scripts/import_cards.py` 落地**：默认 dry-run、`--apply` 落库；字段映射记入 audit_log（detail→observation、feeling→experience、analysis→interpretation、judge_reason→judgement、concrete→evidence_strength、writing→writing_value、help→author_interest、unique→reuse_value）；证据绑定=原话去空白后在窗口行区间内逐字命中 segment，命中 0 条拒绝入库；同 episode+同 quote 幂等跳过。集成测试 3 条全过（tests/integration/test_import_cards.py），dev 库 dry-run 预演 33 卡全部有锚点可入库。
- **最新 commit**：`8a873ca`（import_cards 落地）。上一个 `1327c33`（联网规矩修订+33卡重核）。
- **产出在 `data/dev/exports/cards/`（20260913 后缀）**：两份草稿（正式版/8月更新）+ 两份 human_check（各 14 条待填）+ `cards-state-20260913.json`。

### craft_cards 历史大升级（2026-09-12，全部已 verify+push，别回退）
1. 报告一律**按游戏+版本一份文件**（screen_windows 工作台、coarse_gate 粗判台、human_check 同步拆分）；文件头有「系列｜游戏｜版本」门牌行（系列从库查，无系列显示 —）；
2. **跨版本双向引用自动化**：`auto_link_cross_version()` 两个信号——孪生窗口（两版本窗口原文相似≥0.6）+ 稀有主题词共现（主题字段纯汉字二元组、本批出现≤3卡、共享≥1个），命中即双向挂「相关联卡」行。曾试过全文本相似度和详情词共现两版，因配对太滥/太哑弃用，别改回去；
3. **对齐用户贴的素材卡提示词规范**：联网策略只用四值枚举（重点联网/条件联网/顺带核对/不联网）；说话人=玩家且置信度高才标"玩家原话"；自我反转卡渲染 `- 反转:参见素材卡 NN`；human_check 每条带**卡内原话+原文上下文±2句（按版本精确取源）**。
4. **版本对比卡**：8月更新"新地图感受不到"（高）、正式版"炮手疑似被削"（中）——用户明确要这类卡，铺量时注意从转录里挖跨版本对比语句。
5. **human_check 末尾有「提交状态：（待填写）」+ 完成标准**：条数按实际条目生成；归档前的机器验证=文件内搜「（待填写）」为 0 处且提交状态=已填写，不通过不改名归档。用户明确要过这个标记，别删。
6. **web_log 渲染时程序自动剥离"待人工："前缀**（human_check 和卡片"核对记录"两处）——用户两次圈出重复前缀，此为双保险的程序侧，别删。

### 素材卡自动化三件套（2026-09-12 落地，全部已 verify+push）
1. `scripts/screen_windows.py`——规则召回+窗口合成。8 类信号词库（好评/差评/惊讶/困惑/学会/失败/判断/细节）、命中合并成窗口（±20 句邻域、近距 10 句再合并、不跨集）、**双分制**：总分≥3 入围（保召回），**密度分排序**（每类每窗最多计 2 次 ÷ 句数×10，消"话多红利"和嚎叫刷分）。产出每游戏工作台 + `windows-<日期>.jsonl`。
2. `scripts/coarse_gate.py`——本地双模型粗判门控。**主判官 qwen3:4b-instruct-2507-q4_K_M**（Ollama，JSON schema 强制格式，KEEP/MAYBE/DROP+8 信号标签+重要度0~3+置信度，约3.3秒/窗）；**复核员 deepseek-r1:latest** 只接争议件（密度前30%但4B没给KEEP）。判定落 `gate-state.json` 断点续跑；产出精读名单 `readlist-<日期>.jsonl` + 粗判工作台。
3. `scripts/craft_cards.py`——精读产卡第三层。读精读名单出素材卡草稿；**三道程序锁**：原话逐字锁（引文必须在窗口原文逐字命中，不中重试一次再不中进 human_check）、同窗去重、schema 限 0~3 卡（注意：Ollama 不执行 maxItems，代码里还要去重兜底）。支持 `--from-json`（AI/人工直产卡走同一套锁和渲染）。证据位置由程序从锚点填，模型无权填。
- **本地模型岗位表（三轮考试定案，别再回退）**：qwen3-4B-Instruct=主判官；deepseek-r1 7.6B=复核员+贴标签；qwen3:1.7b/0.6b 判断岗否决；qwen3-embedding:0.6b 用通用锚点分不开高低，等有真实素材卡后再试。
- **版式已对齐用户旧格式（别改回去）**：文件名《游戏》素材卡草稿（版本名）-日期.md；文档骨架=来源说明→"先读我：张力10秒版"→"现在只做这3件事"→价值概览→高/中/低三档分组（组内总分降序，同分按玩家帮助→判断增量→独特性）→文末提交状态；卡头=基础价值/分项（"名称 **分数**"竖线式，最高分加粗）/建议用途/联网策略/判断理由/机会价值；human_check 每轮全量重写。

## 四、下一步计划（主线）

**第 7 步主体：铺量制卡。** 顺序：

1. **用户验收 33 张卡 + 回填 human_check**（`data/dev/exports/cards/` 两份 20260913 草稿 + 两份 human_check，各 14 条待填，含：日期 25号 vs 官方 8月26日 V0.6.11b、『美杜莎之眼』、『难度解绑』、『修改器合规性』、Steam 评测原文待回查）。验收通过并回填 → 改名归档（05 文档流程）。
2. **`scripts/import_cards.py --apply` 把 33 卡写进库**（代码已就绪，只等验收）。
3. **重新导入其他游戏**：旧 29 源已清空，需要用户把原 txt 放进 `data/dev/inbox/auto/`（命名 `系列 - 游戏 - 版本.txt`）或拖 drop-import-dev.bat，然后分类+切集+筛窗+粗判逐游戏铺量，产出按"一游戏+版本一份文件"。
4. **跨游戏关联（方案已定案写入 05 文档，待实现）**：三个信号按确定性排序——①玩家明说提到其他游戏→当场画 cross_reference 线，只关联本地库已有的游戏，外部游戏提及只记卡字段不建档案，等它进库后重跑匹配自动补线；②内容相似→素材卡语义匹配（qwen3-embedding 在第二个游戏产卡后复测，孪生卡当正样本）；③联网联想提前到素材卡阶段（按游戏一轮非逐卡）。落地顺序：验收 33 卡 → 写库 → 新游戏产卡（带信号1）→ embedding 复测 → 联网联想。
5. **规则权重校准（待数据）**：8 类信号词权重目前仍是手拍，等人工勾选积累一批真卡后做回归：哪类信号真的预测"采用"。
6. **联网模型可选升级**：用户哪天给 API key（Kimi/GLM 等），craft_cards 改环境变量即可换强模型。

**之后的路线**：第 8 步起打标签/建关联 → 第 10 步后建写作项目 → claims（必须绑素材卡）→ 角度 → 主题（**必须用户拍板，是人工关卡**）→ 提纲 → 文章。再往后才是灵感卡（第 16 步）。

**已获用户授权的决策方式（重要）**：琐碎判断（如"第二发言人是谁""test 文件跳过"）**AI 直接定、直接干**，把依据写进 audit_log，报表里告知结论即可；**不要逐项请用户拍板**（用户明确说过"太繁琐了"）。方案级的事（改流程、改分档规则）仍需先出方案确认。

**本地 Ollama 现在的岗位**：粗判门控常驻（4B 主判 + r1 复议）。必须 JSON schema 强制格式 + 固定 seed（seed=42），能用规则的绝不请模型，能本地的不上联网。

## 五、踩过的坑（绝对不要再踩）

1. **测试"报红"先分清脚本错还是代码错**：三轮组合测试里所有"失败"全是测试脚本自身错。代码至今零冤案。**先复核测试用例再改代码。**
2. **便携 Python 3.13.12 无 tkinter** → 弹窗必须用系统 Python 3.13.15。
3. **`scripts/gws.py` 会遮蔽 `gws` 包名** → 测试脚本里 import drop_dialog 要用 `importlib.util.spec_from_file_location` 按路径加载，不能 `sys.path.insert('scripts')`。
4. **中文 txt 编码探测必须 strict**：`raw.decode(enc, errors="ignore")` 永不抛异常，不能用来试编码。顺序 utf-8 → gbk → gb18030，先处理 BOM。
5. **CLI `--env` 默认值曾写死 dev 压掉 GWS_ENV** → 已改为 `os.environ.get("GWS_ENV", "dev")`，别改回去。
6. **executescript 隐式 COMMIT** → 迁移执行要显式 BEGIN/COMMIT 包裹。
7. **SQLite NULL ≠ NULL** → `UNIQUE(series_id, name)` 挡不住独立游戏同名，003 的 partial unique index 已封，别删。
8. **purge 级联单环 SQL**：`WHERE col IN (同表子查询)` 永空，len==1 要直接 `WHERE col=?`。
9. **枚举值唯一注册表**：status/speaker/content_type/ref_type 的合法值冻结在 AGENTS.md，禁止在代码里散落新写法。
10. **结构改动唯一合法路径**：新增编号迁移文件（migrations/00X_xxx.sql）→ 过 verify。禁止 rename 表/列、禁止复用 id、禁止删列。`tests/integration/test_schema_contract.py` 把 22 表列名钉死，改名即 FAIL。
11. **不要重跑已完成的上游阶段**；改代码后必跑 `PYTHONPATH=src python scripts/verify.py`（七步门禁），全 PASS 才算完。
12. **GitHub 推送被拒（403 denied to QUEQUE0926）**= 令牌缺 Contents 权限或代理端口变了，先查这两样，别瞎重试。连续失败 2 次停手写 REVIEW_REQUEST.md。
13. **REVIEW_REQUEST.md 是活文档**：新阻塞追加新段，别删旧记录。
14. **清空数据库 = 逐表 DELETE 业务数据，`schema_migrations` 表绝对不能清**：清了它库就"失忆"，下次导入会重放迁移，003 的 `ALTER TABLE ADD position` 报 duplicate column name。修复方式=把缺的 (version, name) 记录补回该表（名称对应 migrations/*.sql 文件名去掉编号前缀）。
15. **本环境删除文件会被 genie-trash 安全机制拦截**（I 盘无回收站，fail-closed），且被占用的文件 mv 不动 → "清空/删除"优先用逐表 DELETE 或先 cp 备份。
16. **printf 写含 `\U`/`\f` 的 bat 会被转义吃掉** → 写 Windows bat 用 Write 工具，不用 shell printf。
17. **拷贝 WAL 模式的 SQLite 库不能直接 cp app.db**（会丢未合并数据）→ 用 Python `sqlite3` 的 `src.backup(dst)` 接口拷。
18. **转写工具的"发言人1/2"只当线索不当真相**：按文件级映射处理（星际2 发言人2→game_audio、镇邪Ⅱ 发言人2→teammate），误归属一条 UPDATE 翻转即可。
19. **ASR 同音变体**：游戏名在台词里会被转错，游戏提及巡逻靠 game_aliases 花名册，发现变体就补别名登记，别改代码。
20. **断行粒度跨源差异巨大**：长度信号只能做"文件内部相对值"（如每集 p90），禁止用绝对阈值。
21. **报告呈现规矩（用户否决过的方案不要再提）**：① 提名报告**每个游戏一份工作台**；② 分档按**每游戏内部相对分**；③ 仓库根 `exports/` **不碰、不做镜像同步**；④ 报告只显示命中句引文，噪音行不进报告。
22. **AGENTS.md 唯一注册表已扩到 8 组枚举**：source_type / tags.category / asset_type / consumer_type，代码里禁造同义词。
23. **created_at 只有秒级精度** → 一切"按时间兜底"的排序必须再补 `rowid`。
24. **make_episodes 的幂等跳过是源级**（commit 9783eec）：跳过判断按该源自己的 segments 是否已在 episode_segments 里。注意 `--source` 前缀匹配会撞同批导入的源（UUIDv7 时间前缀相同），精确指定用完整 id。
25. **classify_speakers.py / make_episodes.py 都支持 `--source <id前缀>`** 可选过滤。
26. **qwen3 系列默认"思考模式"**：不关思考会烧光 num_predict 输出空串。要么请求里 `"think": false`，要么用 JSON schema（`"format": {...}`）。
27. **本地模型的判断岗位已定，不要回退**：主判=qwen3:4b-instruct-2507；自由文本格式让 r1 解析失败——**结构化输出必须 Ollama JSON schema 铐住**，且 schema 的 maxItems 它不执行，数量上限和去重要代码自己兜。
28. **screen_windows 双分制别改回**：总分只做入围门槛（≥3），排序用密度分。曾实测总分与窗口长度相关 r=0.68。单句反转正则已撤。
29. **窗口匹配键必须含 source_id**：同版本多源时集名和行号会完全一样，按集名+行号匹配会配错窗口。
30. **原话逐字锁对谁都生效**（去空白后引文必须命中窗口原文），AI 直产卡（--from-json）也一样要过锁；不中的重试一次，再不中进 human_check，绝不静默入库。
31. **human_check 每轮全量重写**，且必须登记两类：逐字锁失败 + 各卡 web_log 里"待人工"项。用 `if human_check:` 只在有失败时写文件，会留旧账坑人（踩过）。
32. **大段 Edit/补丁后必须 `ast.parse` + grep 检查**：会话里出现过替换引入乱码字和弯引号破坏语法。
33. **git push 连接失败**：先重试一次（代理偶发抖动）；再失败 netstat 查代理端口（7890 曾失效换端口），连续 2 次失败按规矩停手写 REVIEW_REQUEST.md。
34. **联网规矩（2026-09-13 大修订，取代旧版来源规矩）**：事实核验与社区佐证/扫描分轨，等级措辞冻结在 05 文档「联网规矩」节，每条强制三件套（结论+链接+来源页逐字片段）。小黑盒专属链路：匿名搜索不可用，必须走社区 id→话题流——零联网查 `I:\AIstore\13.xhhcatch\xiaoheihe_anonymous_ai_project_docs\data\xhh.db` 的 topic_catalog（灰烬之国=665862 已实测通，20 帖存 `data/dev/tmp/xhh_665862_feed.json`），不联网找 id 不猜 id，查不到停手转 human_check。知乎专栏会 403（已记录，不硬闯）。**Steam 商店页/新闻 API 本机可直连（走 urllib + 空 ProxyHandler + verify=False 的 ssl context，不走代理）**，代理 7890 对 store.steampowered.com 反而连不上。
35. **管线脚本不支持 `--help`**：screen_windows / coarse_gate / craft_cards 传 `--help` 会当真开跑（craft_cards 会真调 LLM 烧时间）。看用法读脚本头部 docstring。
36. **classify_speakers.py 和 make_episodes.py 默认试跑不落库，必须加 `--apply`**。跑完 screen_windows 报"0 个游戏 0 窗口"，第一嫌疑就是分类没落库。重切某源要先 DELETE 该源的 episode_segments 和对应 episodes。
37. **app.db 可能被无名系统进程占用删不掉**（WinError 32）→ 清库别硬删文件，用逐表 DELETE 业务数据（`schema_migrations` 绝对不清）。
38. **重切集会移动窗口锚点**：make_episodes 每集段数微调后 line_start 全变，`my_cards.json` 里的窗口键失效。解法=重映射：对每个卡组找"同源且全部 quote 逐字命中"的新窗口，改键后重跑 `--from-json`。quote 是逐字锁和回查的锚，原文没变它就不会失效。
39. **`data/` 不进 git**：只改卡、改报告时 `git commit` 会是 "nothing to commit"，正常；只有 src/scripts/migrations/HANDOFF 等代码文档变更才有存档点。
40. **写卡数据的标点规矩**：web_log/联网字段里不要自己带"待人工："前缀——craft_cards 渲染时会自动剥离（程序侧双保险），但数据干净少踩坑。卡内标点用直角引号『』，quote 必须与转录逐字一致（含错别字），预先用 norm+find 自查一遍再送渲染。
41. **segments 表的行区间列是 `line_start`/`line_end`**（不是 line_number）——import_cards 查 segment 时踩过。写库类脚本（import_cards）风格：默认 dry-run、`--apply` 落库、写 audit_log。
42. **小黑盒链路依赖**：跑 xhh 客户端要先 `pip install pyyaml`（config 用 yaml）；环境会打印"curl_cffi 未安装退回 httpx"的警告，属正常。

## 六、验证方式速查

```bash
# 全量门禁（必跑）
cd I:\AIstore\game_writing_system_plan_v1
PYTHONPATH=src "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" scripts/verify.py

# 隔离临时库测试（不碰 dev/test/prod）
GWS_RUNNING_TESTS=1 GWS_DATA_ROOT=$(mktemp -d) PYTHONPATH=src <python> - <<'EOF' ... EOF

# CLI 用法
python scripts/gws.py find 名字     # 先看门牌再干活
python scripts/gws.py list
GWS_ENV=test python scripts/gws.py ...   # 环境变量优先生效
```

**每日工作日志**：`.workbuddy/memory/`（2026-09-11、2026-09-12 有细节）。工程纪律见 `02_ENGINEERING_RULES.md`，数据模型见 `03_DATA_MODEL.md`，素材卡系统见 `05_MATERIAL_CARD_SYSTEM.md`，AI 门规见 `AGENTS.md`。

**本仓库 git 常用命令**（先 `git status` 确认当前在哪个分支再操作）：
```bash
GIT_TERMINAL_PROMPT=0 git push          # 推当前分支（代理已配）
git add -A && git commit -m "说明"       # 存档点（在 dev 上打）
# main 只在用户批准后合并：git checkout main && git merge dev && git push && git checkout dev
```
