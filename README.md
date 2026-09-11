# 游戏体验素材资产与写作辅助系统 — 工程仓库

设计方案见 00–16 号文档。本仓库遵循 `02_ENGINEERING_RULES` 契约。

## 常用命令

```bash
# 一键验收（每次修改后必须 ALL CHECKS PASSED）
python scripts/verify.py

# 初始化 / 查看环境（dev | test | prod）
python scripts/gws.py init --env dev
python scripts/gws.py info --env test
```

## 环境隔离

| 环境 | 数据目录 | 用途 |
|------|----------|------|
| dev  | `data/dev/`   | 日常开发（默认） |
| test | `data/test/`  | 自动化测试（verify 内部一律使用临时目录，更严格） |
| prod | `data/prod/`  | 生产数据，测试进程禁止进入 |

每个环境物理隔离：SQLite / raw / exports / logs / backups / tmp。
可用 `GWS_DATA_ROOT` 整体覆盖数据根目录（prod 环境下禁止覆盖）。

## 目录结构

```
src/gws/            领域代码
  config.py         环境隔离配置
  ids.py            UUIDv7 稳定 ID（单调、永不复用）
  db.py             SQLite 连接（foreign_keys/WAL/NORMAL）
  migrations.py     Migration runner
  import_service.py TXT → Source → Segment 最小导入链
migrations/         001_initial.sql 起，NNN_name.sql 命名
scripts/            gws.py CLI、verify.py 一键验收
tests/unit|integration|golden/  三层测试
```

## 硬性纪律（违反即返工）

- Schema 只能通过新增 `migrations/NNN_xxx.sql` 修改，禁止删库重建。
- 测试禁止触碰生产数据；verify 全部跑在临时目录。
- 禁止大爆炸式重构；Expand → Migrate → Switch → Contract。
- 每个严重 Bug 修复必须新增回归用例。
- 只有 `verify` 输出 ALL CHECKS PASSED 才算验收通过。
