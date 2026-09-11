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

### 架构（全部已落地、verify 全 PASS，约 41+ 测试）
- **环境隔离**：`data/<dev|test|prod>/` 三套物理隔离 SQLite，各含 `app.db、raw/、inbox/、exports/、backups/、tmp/`。测试必须用 test 环境或临时目录（`GWS_RUNNING_TESTS=1` + `GWS_DATA_ROOT=$(mktemp -d)`），**禁止拿生产数据测试**。
- **Schema**：22 张表。001 建 21 表 + 002 加 `game_aliases`（别名全库唯一）+ **003 加固**（games 两个 partial unique index 封独立游戏同名 NULL 漏洞、episode_segments 加 position 列）。当前 schema version = 3。
- **主拓扑**：`series → games → game_versions → sources → segments`，全部靠 **UUIDv7 稳定 id** 外键关联，name 只在导入入口解析一次用。下游还有 episodes / material_cards / claims / articles 等已建表（空房待入住）。
- **状态机**：长期实体表有 status（active/archived/deprecated/trashed，trashed 是终点且拒新引用）；5 张纯关系表（episode_segments、material_card_evidence、asset_tags、claim_evidence、project_assets）**无 status**，直接删 + audit_log。

### 入口（用户日常使用方式）
1. **拖放弹窗**：拖 txt 到 `drop-import-dev.bat` / `drop-import-prod.bat` → tkinter 弹窗预填（系列/游戏/版本），**边填边实时查库**（绿色=复用/新建明细，红色=冲突/重复警告），点导入再弹确认框 → 源文件**原地不动**，复制副本到 `data/<env>/inbox/drop-import/` → 导入成功自动删副本，失败保留副本排查。注意：bat 必须指向**系统 Python**（`C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`），便携版 3.13.12 无 tkinter。
2. **prepare / auto-import**：inbox 扫描自动导入。
3. **CLI**（`scripts/gws.py`）：`init / info / create-* / import-txt / import-files / rename-*/ add-alias / find / list / export-html`。`find <名字>` 模糊查三类档案并排显示门牌（系列→游戏→版本）+ id，多命中绝不猜。

### 关键业务规则
- 命名规范：`系列 - 游戏 - 版本.txt`（无系列则 `游戏 - 版本.txt`），默认系列=游戏名，`#N` 为同版本多实况序号。
- 匹配 `_resolve_target`（src/gws/auto_import.py）：显式系列 → 严格系列内匹配；默认系列 → 先找同名系列，否则全局主名→别名，**唯一命中才复用，多命中报错不猜，零命中新建**。
- 去重：同版本 + 相同 sha256 → 跳过。
- rename 自动留旧名为别名；purge：级联软删 owned-children → 备份 → confirm 后物理删除。
- 导入只接受 `.txt`（docx 支持已按用户要求撤销）。
- 只读原文归档：`data/<env>/raw/<sha前2位>/<sha>.txt`，永不覆盖。

## 三、当前卡在哪

**没有卡点。** dev/prod 均为干净空库（用户确认清空过），随时可投喂真实 TXT。

## 四、下一步计划（主线）

**按 14_MVP_TASKS / 15_IMPLEMENTATION_ORDER，下一步是第 4 步：Speaker 分类** —— 把 segments 的 speaker 从 `unknown` 分类到 8 类（author / teammate / npc / ui / subtitle / game_audio / system / unknown，枚举已冻结在 AGENTS.md）。之后是第 5 步 Episode 切分。

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
