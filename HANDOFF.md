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
- **主拓扑**：`series → games → game_versions → sources → segments`，全部靠 **UUIDv7 稳定 id** 外键关联，name 只在导入入口解析一次用。下游还有 episodes / material_cards / claims / articles 等已建表（空房待入住）。
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

## 三、当前状态（2026-09-12 晚三次更新）

**没有卡点。主线：第 1~6 步完成；第 7 步素材卡制作中（提名已出，等用户勾选）。**

- **dev 库真实数据（2026-09-12 晚）**：26 系列 / 27 版本 / 29 个源 / 约 3.3 万句台词。**已完成分类+切集的源 14 个**（原 6 个 + 本轮 7 个 + 星际2 复扫）：镇邪Ⅱ、星际裂变×2、星际2、沃德灵、银翼喵侍、Apex 训练场（20集）、Good Heavens（10集）、Subnautica2 源a（35集）、Yerba Buena（4集）、地狱公主（24集）、灰烬之国正式版（14集）、灰烬之国8月更新（9集）。切集总数 77+116=193 集左右。
- **剩余未处理源约 15 个**（三国朋克 3031 句、双影奇境 4901 句、苏丹的游戏 1110 句等），要跑时用户说了算。
- **第 7 步素材卡**：提名工具跑完三遍规则扫描，391 个候选在 `data/dev/exports/nominations/`。注意：提名只覆盖旧 6 源，新导入的 23 个源还没提名，制卡前可能要重跑提名扫描。
- **总览页**：`data/dev/exports/dev_games_overview.html`（按 sort_key 排序，含各源台词数）。
- **工作分支常驻 dev**。dev 分支最新 commit：`234f2d0`。
- prod 仍是干净空库。
- 遗留小瑕疵（不急，用户未拍板）：① 银翼喵侍的版本名是 `dmeo`（demo 打错）；② 星际裂变下挂着一个 159 字节的 test 小文件（3 句台词）。

## 四、下一步计划（主线）

**第 7 步主体：素材卡制作。** 用户从提名工作台（`data/dev/exports/nominations/`）勾选候选（`- [ ]` 勾成 `- [x]` 或直接回编号），然后按 `05_MATERIAL_CARD_SYSTEM.md` 的"提炼约定（2026-09-12 节）"制卡：

- **subject = 15 字内钩子坯**（标题弹药库）、**quote = 逐字原话**、**无 judgement 的卡不收**、四维评分随手打；
- 挑卡时刻意留意"反转瞬间"（真香/翻车/两游戏打架），制卡时挂 `cross_references` 的 contrasts/contradicts——张力层零新增成本；
- 制卡需要新写卡片创建代码（repositories 里还没有 material_cards 写入基础设施），走新迁移不许动结构。

**之后的路线**：第 8 步起打标签/建关联 → 第 10 步后建写作项目 → claims（必须绑素材卡）→ 角度 → 主题（**必须用户拍板，是人工关卡**）→ 提纲 → 文章。再往后才是灵感卡（第 16 步）——按"先有靶点再出去找东西"的时序押后。

**已获用户授权的决策方式（重要）**：琐碎判断（如"第二发言人是谁""test 文件跳过"）**AI 直接定、直接干**，把依据写进 audit_log，报表里告知结论即可；**不要逐项请用户拍板**（用户明确说过"太繁琐了"）。方案级的事（改流程、改分档规则）仍需先出方案确认。

**本地 Ollama 使用时机**：规则漏抓严重时才启用（说话人二扫 / 残余 unknown 细筛 / 提卡草稿）。必须带固定 seed + 幻觉守卫（见用户长期记忆），能用规则的绝不请模型。

## 五、踩过的坑（绝对不要再踩）

1. **测试"报红"先分清脚本错还是代码错**：三轮组合测试里所有"失败"全是测试脚本自身错（拿已导入内容测"新实况"、期望值算漏系列、拿新名撞旧名别名）。代码至今零冤案。**先复核测试用例再改代码。**
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
13. **REVIEW_REQUEST.md 是活文档**：2026-09-12 那条 403 阻塞已结案（✅ 段留在文件里），新阻塞追加新段，别删旧记录。它还没进 git 存档，下次 dev 存档时一起 `git add`。
14. **清空数据库 = 逐表 DELETE 业务数据，`schema_migrations` 表绝对不能清**（2026-09-12 血泪坑）：清了它库就"失忆"，下次导入会重放迁移，003 的 `ALTER TABLE ADD position` 报 duplicate column name: position。修复方式是把缺的 (version, name) 记录补回该表（名称对应 migrations/*.sql 文件名去掉编号前缀）。
15. **本环境删除文件会被 genie-trash 安全机制拦截**（I 盘无回收站，fail-closed），且被占用的文件 mv 不动 → "清空/删除"优先用逐表 DELETE 或先 cp 备份；单次 git push 403 若令牌权限已修好，先重试一次再排查（代理偶发抖动）。
16. **printf 写含 `\U`/`\f` 的 bat 会被转义吃掉** → 写 Windows bat 用 Write 工具，不用 shell printf。
17. **拷贝 WAL 模式的 SQLite 库不能直接 cp app.db**（会丢未合并数据，表现是"只查出一半"）→ 用 Python `sqlite3` 的 `src.backup(dst)` 接口拷，沙盒试跑一律走这条路。
18. **转写工具的"发言人1/2"只当线索不当真相**：它分得清"不同声音"，分不清"是真人还是游戏语音"。按文件级映射处理（星际2 发言人2→game_audio、镇邪Ⅱ 发言人2→teammate，依据已记 audit_log），发现整文件映射反了一条 UPDATE 翻转即可。误归属影响极小（只改枚举值），别为此大动干戈。
19. **ASR 同音变体**：游戏名在台词里会被转错（镇邪Ⅱ→"正邪"出现过 7 次），游戏提及巡逻靠 game_aliases 花名册，发现变体就补别名登记，别改代码。
20. **断行粒度跨源差异巨大**（行中位数 4~29 字，银翼喵侍 34% 超 80 字）：长度信号只能做"文件内部相对值"（如每集 p90），禁止用绝对阈值（40 字算长句之类）。
21. **报告呈现规矩（用户否决过的方案不要再提）**：① 提名报告**每个游戏一份工作台**，不堆一个大文件；② 分档按**每游戏内部相对分**（高=前30%，且详情首屏上限 20 张，第 21 名起降入单行备查）；③ 仓库根 `exports/` **不碰、不做镜像同步**（用户明确否决）；④ 报告只显示命中句引文，`[game_audio]`/"发言人N"噪音行不进报告。
22. **AGENTS.md 唯一注册表已扩到 8 组枚举**（2026-09-12 用户批准）：新增 source_type / tags.category / asset_type / consumer_type，和 03_DATA_MODEL.md 的枚举表对齐，代码里禁造同义词。
23. **created_at 只有秒级精度**，同一秒建档的两行 ORDER BY created_at 会打平、顺序随机 → 一切"按时间兜底"的排序必须再补 `rowid`（2026-09-12 sort_key 上线时 verify 抓出过）。
24. **make_episodes 的幂等跳过是"版本级"**：同版本多个源时，该版本跑过一次切集后，另一个源会被整体跳过（Subnautica2 源b 2223 句就卡在这）。要给同版本第二源切集，先把跳过逻辑改成源级再跑。
25. **classify_speakers.py / make_episodes.py 都支持 `--source <id前缀>`** 可选过滤（只处理命中的源），批量跑单源用它；不带参数仍是全库扫。

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

**每日工作日志**：`.workbuddy/memory/2026-09-11.md`、`2026-09-12.md`（有本轮全部细节）。工程纪律见 `02_ENGINEERING_RULES.md`，数据模型见 `03_DATA_MODEL.md`，AI 门规见 `AGENTS.md`。

**本仓库 git 常用命令**（先 `git status` 确认当前在哪个分支再操作）：
```bash
GIT_TERMINAL_PROMPT=0 git push          # 推当前分支（代理已配）
git add -A && git commit -m "说明"       # 存档点（在 dev 上打）
# main 只在用户批准后合并：git checkout main && git merge dev && git push && git checkout dev
```
