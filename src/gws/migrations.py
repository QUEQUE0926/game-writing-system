# -*- coding: utf-8 -*-
"""Migration Runner（02_ENGINEERING_RULES §3）。

- 数据库从第一天带 schema version（schema_migrations 表）。
- 使用 migrations/001_initial.sql、002_xxx.sql... 顺序应用。
- 每个 migration 在单独事务中执行，失败即回滚，不留下半套 schema。
- 幂等：已应用的 migration 不会重复应用。
- 禁止删除 app.db 重建作为升级方案——升级只能走这里。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_NAME_RE = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")


def list_migrations() -> list[tuple[int, str, Path]]:
    """返回 [(version, name, path)]，按版本号升序。"""
    found = []
    for p in MIGRATIONS_DIR.glob("*.sql"):
        m = _NAME_RE.match(p.name)
        if not m:
            raise ValueError(f"迁移文件命名不合法（应为 NNN_name.sql）: {p.name}")
        found.append((int(m.group(1)), m.group(2), p))
    found.sort(key=lambda x: x[0])
    versions = [v for v, _, _ in found]
    if len(versions) != len(set(versions)):
        raise ValueError("迁移版本号重复")
    return found


def ensure_schema_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 0


def migrate(conn: sqlite3.Connection) -> list[int]:
    """应用所有待执行迁移，返回本次实际应用的版本号列表。"""
    ensure_schema_table(conn)
    done = applied_versions(conn)
    applied_now: list[int] = []
    for version, name, path in list_migrations():
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        # executescript 会隐式 COMMIT 掉挂起事务，因此把事务放进脚本本身，
        # 保证单个 migration 要么完整生效、要么完整回滚。
        try:
            conn.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied_now.append(version)
    return applied_now
