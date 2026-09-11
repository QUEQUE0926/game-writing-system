# -*- coding: utf-8 -*-
"""环境隔离配置：DEV / TEST / PROD。

规则（对应 02_ENGINEERING_RULES §2）：
- 必须同时隔离 SQLite、Raw storage、Config、Cache、Exports、Logs、Temp。
- 禁止仅修改程序名而共用真实数据。
- 测试永远不允许触碰 prod 数据目录。

环境选择：
- 环境变量 GWS_ENV = dev | test | prod（默认 dev）。
- 环境变量 GWS_DATA_ROOT 可整体覆盖数据根目录（仅 dev/test 允许，用于迁移测试临时目录）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID_ENVS = ("dev", "test", "prod")


class Config:
    def __init__(self, env: str, data_root: Path):
        self.env = env
        self.data_root = data_root
        # 每个环境独立的物理目录：SQLite / Raw / Exports / Logs / Backups / Temp
        self.db_path = data_root / "app.db"
        self.raw_dir = data_root / "raw"
        # inbox：用户原始素材暂存区（<游戏名>/<版本>/*.txt），系统只读不改
        self.inbox_dir = data_root / "inbox"
        self.exports_dir = data_root / "exports"
        self.logs_dir = data_root / "logs"
        self.backups_dir = data_root / "backups"
        self.tmp_dir = data_root / "tmp"

    def ensure_dirs(self) -> None:
        for d in (
            self.data_root,
            self.raw_dir,
            self.inbox_dir,
            self.exports_dir,
            self.logs_dir,
            self.backups_dir,
            self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def load_config(env: str | None = None) -> Config:
    """加载指定环境的配置；不允许测试进程进入 prod。"""
    env = (env or os.environ.get("GWS_ENV") or "dev").strip().lower()
    if env not in VALID_ENVS:
        raise ValueError(f"未知环境: {env!r}，必须是 {VALID_ENVS} 之一")

    # 显式参数 > 环境变量覆盖 > 默认仓库内 data/<env>
    data_root_env = os.environ.get("GWS_DATA_ROOT")
    if data_root_env:
        if env == "prod":
            # 严禁把 prod 指到临时/共享目录，防误操作
            raise PermissionError("GWS_DATA_ROOT 覆盖在 prod 环境下被禁止")
        data_root = Path(data_root_env).resolve()
    else:
        data_root = (REPO_ROOT / "data" / env).resolve()

    if os.environ.get("GWS_RUNNING_TESTS") == "1" and env == "prod":
        raise PermissionError("测试进程禁止使用 prod 环境")

    return Config(env, data_root)


def is_test_process() -> bool:
    return os.environ.get("GWS_RUNNING_TESTS") == "1" or "unittest" in sys.modules
