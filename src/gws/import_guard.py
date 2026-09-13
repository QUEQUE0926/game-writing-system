# -*- coding: utf-8 -*-
"""导入防线（2026-09-13 用户拍板①②）：

- **版本名相似提醒**：新建版本时，同游戏下已有名字高度相似的版本
  → 提醒手误可能（如已有「8月更新」要建「8跟新」）；
- **同内容跨版本提醒**：文件内容与该游戏另一版本下已有实况完全相同
  → 提醒重复导入。

只提醒、不拦截：确认是正常新建时忽略警告即可。判定逻辑与措辞在
drop_dialog 预告、CLI 输出、auto_import 结果三处共用本模块。
"""
from __future__ import annotations

import difflib
import sqlite3

_RATIO = 0.5


def _suspicious(a: str, b: str) -> bool:
    """两个版本名是否像手误：互相包含，或相似度达标且差异不全是数字。"""
    a, b = a.strip(), b.strip()
    if not a or not b or a == b:
        return False
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return True
    sm = difflib.SequenceMatcher(None, a, b)
    if sm.ratio() < _RATIO:
        return False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # 差异全是数字（V1→V2 这类正常版本递进）不算手误
        if a[i1:i2].isdigit() and b[j1:j2].isdigit():
            continue
        return True
    return False


def version_name_suspects(conn: sqlite3.Connection, game_id: str,
                          ver_name: str) -> list[str]:
    """同游戏下与 ver_name 疑似手误的现有版本名（升序）。"""
    rows = conn.execute(
        "SELECT name FROM game_versions WHERE game_id=? "
        "AND status!='trashed'", (game_id,)).fetchall()
    return sorted(r["name"] for r in rows
                  if _suspicious(r["name"], ver_name))


def cross_version_dup(conn: sqlite3.Connection, game_id: str, sha: str,
                      exclude_version_id: str | None = None) -> list[str]:
    """同游戏下已有 sha256 相同实况的其他版本名（升序）。"""
    rows = conn.execute(
        "SELECT DISTINCT v.name AS name FROM sources s "
        "JOIN game_versions v ON v.id = s.version_id "
        "WHERE v.game_id=? AND s.sha256=? AND v.status!='trashed'",
        (game_id, sha)).fetchall()
    names = {r["name"] for r in rows}
    if exclude_version_id:
        row = conn.execute("SELECT name FROM game_versions WHERE id=?",
                           (exclude_version_id,)).fetchone()
        if row:
            names.discard(row["name"])
    return sorted(names)
