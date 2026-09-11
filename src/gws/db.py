# -*- coding: utf-8 -*-
"""SQLite 连接层（13_STORAGE_AND_RECOVERY）。

PRAGMA:
- foreign_keys = ON
- journal_mode = WAL
- synchronous = NORMAL
"""
from __future__ import annotations

import sqlite3

from .config import Config


def connect(cfg: Config) -> sqlite3.Connection:
    cfg.ensure_dirs()
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
