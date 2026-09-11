# -*- coding: utf-8 -*-
"""Repository 层 v0（02 §6 依赖方向：Application → Domain → Repository → SQLite）。

覆盖 MVP 建档链：Series / Game / Version / Source / Segment。
- 创建时做引用校验（目标存在且非 trashed）
- 状态变更走 lifecycle 状态机
- purge 走 引用检查 → 备份 → 确认 → 物理删除（02 §12 / 00 §19）
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import Config
from .ids import new_id
from .validation import (LIFECYCLE_ERROR, REFERENCE_ERROR, ValidationError,
                         in_transaction, validate_reference_target,
                         validate_status_transition)

# Owned-child 反向引用（03_DATA_MODEL：Owned-child 可受控级联进 Trash；
# Reference 关系不得静默级联物理删除——v0 只处理建档链，写作域延后）
_OWNED_CHILDREN: dict[str, dict[str, str]] = {
    "series": {"games": "series_id"},
    "games": {"game_versions": "game_id", "game_aliases": "game_id"},
    "game_versions": {"sources": "version_id", "episodes": "version_id"},
    "sources": {"segments": "source_id"},
    "episodes": {"episode_segments": "episode_id", "material_cards": "episode_id"},
    "material_cards": {"material_card_evidence": "material_card_id"},
    "segments": {"episode_segments": "segment_id",
                 "material_card_evidence": "segment_id"},
}


class Repository:
    table: str

    def __init__(self, conn: sqlite3.Connection, cfg: Config):
        self.conn = conn
        self.cfg = cfg

    # ---- 基础 ----
    def get(self, object_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (object_id,)).fetchone()

    def exists(self, object_id: str) -> bool:
        return self.get(object_id) is not None

    # ---- 生命周期 ----
    def set_status(self, object_id: str, target: str) -> None:
        row = self.get(object_id)
        if row is None:
            raise ValidationError(REFERENCE_ERROR,
                                  f"{self.table}.{object_id} 不存在")
        validate_status_transition(row["status"], target)
        self.conn.execute(
            f"UPDATE {self.table} SET status = ? WHERE id = ?",
            (target, object_id))
        self.conn.commit()

    # ---- 改名（身份是 ID，名字只是展示字段；改名不动任何引用）----
    def rename(self, object_id: str, new_name: str) -> None:
        row = self.get(object_id)
        if row is None:
            raise ValidationError(REFERENCE_ERROR,
                                  f"{self.table}.{object_id} 不存在")
        old_name = row["name"]
        try:
            self.conn.execute(
                f"UPDATE {self.table} SET name = ? WHERE id = ?",
                (new_name, object_id))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(
                REFERENCE_ERROR,
                f"改名冲突：{self.table} 下已存在同名项 {new_name!r}") from None
        # 改名保险：把旧名字留作别名，旧名字的 txt 之后仍能匹配到本档案
        if self.table == "games" and old_name != new_name:
            try:
                self.add_alias(object_id, old_name)
            except ValidationError:
                pass  # 别名已被其他档案占用时保持沉默，不阻断改名

    # ---- Purge（00 §19：Purge → Reference Check → Backup → Confirm → Delete）----
    def _has_status(self, table: str) -> bool:
        cols = {r[1] for r in self.conn.execute(
            f"PRAGMA table_info({table})")}
        return "status" in cols

    def _reference_count(self, object_id: str) -> int:
        """活跃的 owned-child 引用数（trashed 的不计为阻塞；
        无 status 列的附属表如 game_aliases 不算引用、不阻塞）。"""
        n = 0
        for child_table, col in _OWNED_CHILDREN.get(self.table, {}).items():
            if not self._has_status(child_table):
                continue
            row = self.conn.execute(
                f"SELECT COUNT(*) AS c FROM {child_table} "
                f"WHERE {col} = ? AND status != 'trashed'", (object_id,)
            ).fetchone()
            n += row["c"]
        return n

    def _owned_children(self, object_id: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for child_table, col in _OWNED_CHILDREN.get(self.table, {}).items():
            for r in self.conn.execute(
                    f"SELECT id FROM {child_table} WHERE {col} = ?",
                    (object_id,)):
                out.append((child_table, r["id"]))
        return out

    def purge(self, object_id: str, confirm: bool) -> int:
        """物理删除：先受控级联把 owned-children 全部软删进 Trash，
        再备份、再物理删除。必须 confirm=True。返回级联软删的子对象数。"""
        row = self.get(object_id)
        if row is None:
            raise ValidationError(REFERENCE_ERROR,
                                  f"{self.table}.{object_id} 不存在")
        if not confirm:
            raise ValidationError(
                LIFECYCLE_ERROR, "purge 需要 confirm=True（引用检查→备份→确认→删除）")

        cascade = 0
        for child_table, child_id in self._owned_children(object_id):
            if not self._has_status(child_table):
                continue  # 无 status 列的附属表（如别名）直接随物理删除走
            r = self.conn.execute(
                f"SELECT status FROM {child_table} WHERE id=?",
                (child_id,)).fetchone()
            if r["status"] != "trashed":
                self.conn.execute(
                    f"UPDATE {child_table} SET status='trashed' WHERE id=?",
                    (child_id,))
                cascade += 1

        # 备份（02 §12：Purge 前自动备份）；VACUUM 不能在事务内执行
        self.conn.commit()
        self.cfg.ensure_dirs()
        backup_path = self.cfg.backups_dir / \
            f"purge-{self.table}-{object_id[:8]}.db"
        self.conn.execute("VACUUM INTO ?", (str(backup_path),))

        # 物理删除：沿引用链逐层子查询，叶子先删，避免 FK 拦截。
        # 例：purge game → DELETE FROM segments WHERE source_id IN
        #   (SELECT id FROM sources WHERE version_id IN
        #    (SELECT id FROM game_versions WHERE game_id=?))
        def _collect_paths(table: str, chain: list[tuple[str, str]],
                           acc: list[list[tuple[str, str]]]):
            children = _OWNED_CHILDREN.get(table, {})
            if not children:
                if chain:
                    acc.append(chain)
                return
            for child_table, col in children.items():
                _collect_paths(child_table, chain + [(child_table, col)], acc)

        paths: list[list[tuple[str, str]]] = []
        _collect_paths(self.table, [], paths)
        paths.sort(key=len, reverse=True)  # 链长的（更深后代）先删

        def _stmt(chain):
            """链上最后一环为删除目标，其余环组成子查询链。

            单环链直接 WHERE col=?（子查询若与目标同表，IN 永远不匹配）。
            """
            if len(chain) == 1:
                return (f"DELETE FROM {chain[0][0]} WHERE {chain[0][1]} = ?",
                        (object_id,))
            sub = f"SELECT id FROM {chain[0][0]} WHERE {chain[0][1]} = ?"
            for child_table, col in chain[1:-1]:
                sub = f"SELECT id FROM {child_table} WHERE {col} IN ({sub})"
            return (f"DELETE FROM {chain[-1][0]} WHERE {chain[-1][1]} IN ({sub})",
                    (object_id,))

        # 链上每一环都要删（中间节点自己也引用着上游），深的先删
        stmts: list[tuple[int, tuple[str, tuple]]] = []
        for chain in paths:
            for i in range(len(chain)):
                stmts.append((i, _stmt(chain[:i + 1])))
        stmts.sort(key=lambda x: -x[0])
        seen = set()
        ordered = [s for _, s in stmts
                   if not (s[0] in seen or seen.add(s[0]))]

        def _do():
            for sql, params in ordered:
                self.conn.execute(sql, params)
            self.conn.execute(
                f"DELETE FROM {self.table} WHERE id = ?", (object_id,))
        in_transaction(self.conn, _do)
        return cascade


class GameRepository(Repository):
    table = "games"

    def create(self, name: str, series_id: str | None = None) -> str:
        if series_id is not None:
            validate_reference_target(self.conn, "series", series_id, "series_id")
        gid = new_id()
        try:
            self.conn.execute(
                "INSERT INTO games (id, series_id, name) VALUES (?,?,?)",
                (gid, series_id, name))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(
                REFERENCE_ERROR, f"游戏名重复（同系列下）: {name}") from None
        return gid

    # ---- 别名 ----
    def add_alias(self, game_id: str, alias: str) -> str:
        if not self.exists(game_id):
            raise ValidationError(REFERENCE_ERROR,
                                  f"games.{game_id} 不存在")
        aid = new_id()
        try:
            self.conn.execute(
                "INSERT INTO game_aliases (id, game_id, alias) VALUES (?,?,?)",
                (aid, game_id, alias))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(
                REFERENCE_ERROR, f"别名已被占用: {alias!r}") from None
        return aid

    def find_by_name_or_alias(self, name: str,
                              series_id: str | None) -> str | None:
        """在指定系列（或无系列）范围内按 主名 → 别名 匹配；绝不跨系列猜测。"""
        row = self.conn.execute(
            "SELECT id FROM games WHERE series_id IS ? AND name=? "
            "AND status!='trashed' LIMIT 1", (series_id, name)).fetchone()
        if row:
            return row["id"]
        row = self.conn.execute(
            """SELECT ga.game_id AS gid FROM game_aliases ga
               JOIN games g ON g.id = ga.game_id
               WHERE g.series_id IS ? AND ga.alias = ?
                 AND g.status != 'trashed' LIMIT 1""",
            (series_id, name)).fetchone()
        return row["gid"] if row else None

    def find_global(self, name: str) -> list[str]:
        """跨系列按 主名/别名 匹配，返回全部命中（供默认系列场景裁决歧义）。"""
        ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM games WHERE name=? AND status!='trashed'",
            (name,))]
        if not ids:
            ids = [r["gid"] for r in self.conn.execute(
                """SELECT ga.game_id AS gid FROM game_aliases ga
                   JOIN games g ON g.id = ga.game_id
                   WHERE ga.alias = ? AND g.status != 'trashed'""", (name,))]
        return ids

    # ---- 改名时同步默认系列（系列名 == 旧游戏名 且 只挂本游戏 → 一起改）----
    def rename(self, object_id: str, new_name: str) -> None:
        row = self.get(object_id)
        if row is None:
            raise ValidationError(REFERENCE_ERROR,
                                  f"{self.table}.{object_id} 不存在")
        old_name = row["name"]
        series_id = row["series_id"] if "series_id" in row.keys() else None
        super().rename(object_id, new_name)
        if series_id:
            siblings = self.conn.execute(
                "SELECT COUNT(*) AS c FROM games WHERE series_id=? "
                "AND status!='trashed'", (series_id,)).fetchone()["c"]
            srow = self.conn.execute(
                "SELECT name FROM series WHERE id=?", (series_id,)).fetchone()
            if siblings == 1 and srow and srow["name"] == old_name \
                    and old_name != new_name:
                try:
                    self.conn.execute(
                        "UPDATE series SET name=? WHERE id=?",
                        (new_name, series_id))
                    self.conn.commit()
                except sqlite3.IntegrityError:
                    pass  # 新系列名已被占用时保持沉默，系列名不影响身份


class SeriesRepository(Repository):
    table = "series"

    def create(self, name: str) -> str:
        sid = new_id()
        try:
            self.conn.execute(
                "INSERT INTO series (id, name) VALUES (?,?)", (sid, name))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(
                REFERENCE_ERROR, f"系列名重复: {name}") from None
        return sid


class VersionRepository(Repository):
    table = "game_versions"

    def create(self, game_id: str, name: str) -> str:
        validate_reference_target(self.conn, "games", game_id, "game_id")
        vid = new_id()
        try:
            self.conn.execute(
                "INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
                (vid, game_id, name))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(
                REFERENCE_ERROR, f"版本名重复（同游戏下）: {name}") from None
        return vid


class SourceRepository(Repository):
    table = "sources"
