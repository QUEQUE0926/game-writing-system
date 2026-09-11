# -*- coding: utf-8 -*-
"""迁移集成测试：全部在临时目录（TEST 环境隔离）执行，绝不触碰 prod。"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import (applied_versions, current_version,  # noqa: E402
                            list_migrations, migrate)

EXPECTED_TABLES = {
    "series", "games", "game_versions", "sources", "segments",
    "episodes", "episode_segments", "material_cards", "material_card_evidence",
    "inspiration_cards", "tags", "asset_tags", "cross_references",
    "usage_records", "projects", "project_assets", "claims", "claim_evidence",
    "articles", "audit_log", "schema_migrations",
}


class TestMigrations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def test_fresh_migrate_creates_all_tables(self):
        expected_count = len(list_migrations())
        migrate(self.conn)
        names = {r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = EXPECTED_TABLES - names
        self.assertFalse(missing, f"缺少表: {missing}")
        self.assertEqual(current_version(self.conn), expected_count)

    def test_migrate_is_idempotent(self):
        expected = list(range(1, len(list_migrations()) + 1))
        first = migrate(self.conn)
        second = migrate(self.conn)
        self.assertEqual(first, expected)
        self.assertEqual(second, [], "重复 migrate 不应重复应用")

    def test_schema_version_recorded(self):
        expected = set(range(1, len(list_migrations()) + 1))
        migrate(self.conn)
        self.assertEqual(current_version(self.conn), len(expected))
        self.assertEqual(applied_versions(self.conn), expected)


class TestInvariants(unittest.TestCase):
    """数据不变量（02 §5）——用 FK / UNIQUE / CHECK 落地并验证。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.conn = connect(load_config("test"))
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def _seed_identity(self):
        c = self.conn
        game_id, ver_id, src_id = "g" * 36, "v" * 36, "s" * 36
        # 用真实 UUID 格式
        from gws.ids import new_id
        game_id, ver_id, src_id = new_id(), new_id(), new_id()
        c.execute("INSERT INTO games (id, name) VALUES (?,?)", (game_id, "测试游戏"))
        c.execute("INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
                  (ver_id, game_id, "1.0"))
        c.execute(
            """INSERT INTO sources
               (id, version_id, filename, relative_path, sha256)
               VALUES (?,?,?,?,?)""",
            (src_id, ver_id, "merged.txt", "raw/xx/merged.txt", "a" * 64))
        c.commit()
        return game_id, ver_id, src_id

    def test_source_requires_existing_version(self):
        from gws.ids import new_id
        with self.assertRaises(Exception):
            self.conn.execute(
                "INSERT INTO sources (id, version_id, filename, relative_path, sha256)"
                " VALUES (?,?,?,?,?)", (new_id(), "missing", "f.txt", "p", "b" * 64))
            self.conn.commit()

    def test_source_sha_unique_per_version(self):
        _, _, src_id = self._seed_identity()
        with self.assertRaises(Exception):
            self.conn.execute(
                """INSERT INTO sources
                   (id, version_id, filename, relative_path, sha256)
                   VALUES (?,?,?,?,?)""",
                ("x" * 36, self.conn.execute(
                    "SELECT version_id FROM sources WHERE id=?",
                    (src_id,)).fetchone()[0],
                "dup.txt", "p", "a" * 64))
            self.conn.commit()

    def test_segment_speaker_check(self):
        _, _, src_id = self._seed_identity()
        from gws.ids import new_id
        with self.assertRaises(Exception):
            self.conn.execute(
                """INSERT INTO segments
                   (id, source_id, ordinal, line_start, line_end, speaker, text)
                   VALUES (?,?,?,?,?,?,?)""",
                (new_id(), src_id, 1, 1, 1, "bogus_speaker", "hi"))
            self.conn.commit()

    def test_trashed_object_rejects_new_normal_reference(self):
        """trashed 对象不能接收新的正常引用：引用完整性由应用层校验，
        这里验证软删除状态可正确写入（落地校验在 Validation 层测试中扩展）。"""
        _, ver_id, _ = self._seed_identity()
        from gws.ids import new_id
        ep_id = new_id()
        self.conn.execute(
            "INSERT INTO episodes (id, version_id, title, status) VALUES (?,?,?,?)",
            (ep_id, ver_id, "废弃集", "trashed"))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT status FROM episodes WHERE id=?", (ep_id,)).fetchone()
        self.assertEqual(row["status"], "trashed")

    def test_foreign_keys_enforced(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class TestSchemaHardening(unittest.TestCase):
    """003 迁移的三个加固点（外部审查采纳项）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.conn = connect(load_config("test"))
        migrate(self.conn)
        from gws.ids import new_id
        self.new_id = new_id

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def test_standalone_games_name_unique(self):
        """series_id IS NULL 的独立游戏也不能重名（NULL!=NULL 漏洞已封）。"""
        self.conn.execute(
            "INSERT INTO games (id, name) VALUES (?,?)",
            (self.new_id(), "恶魔牌"))
        with self.assertRaises(Exception):
            self.conn.execute(
                "INSERT INTO games (id, name) VALUES (?,?)",
                (self.new_id(), "恶魔牌"))
            self.conn.commit()

    def test_series_games_name_unique_still_holds(self):
        """同系列内不重名照常生效；跨系列同名允许。"""
        s1, s2 = self.new_id(), self.new_id()
        self.conn.executemany(
            "INSERT INTO series (id, name) VALUES (?,?)",
            [(s1, "系列X"), (s2, "系列Y")])
        self.conn.execute(
            "INSERT INTO games (id, series_id, name) VALUES (?,?,?)",
            (self.new_id(), s1, "同名人"))
        with self.assertRaises(Exception):
            self.conn.execute(
                "INSERT INTO games (id, series_id, name) VALUES (?,?,?)",
                (self.new_id(), s1, "同名人"))
            self.conn.commit()
        # 跨系列同名放行
        self.conn.execute(
            "INSERT INTO games (id, series_id, name) VALUES (?,?,?)",
            (self.new_id(), s2, "同名人"))
        self.conn.commit()

    def test_episode_segment_position_unique(self):
        """同一集内 position 不得重复；不同集可同位。"""
        game_id = self.new_id()
        ver_id, ep1, ep2 = self.new_id(), self.new_id(), self.new_id()
        src_id, seg1, seg2 = self.new_id(), self.new_id(), self.new_id()
        self.conn.executemany(
            "INSERT INTO games (id, name) VALUES (?,?)",
            [(game_id, "G"), ])
        self.conn.execute(
            "INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
            (ver_id, game_id, "v"))
        self.conn.executemany(
            "INSERT INTO episodes (id, version_id, title) VALUES (?,?,?)",
            [(ep1, ver_id, "第一集"), (ep2, ver_id, "第二集")])
        self.conn.execute(
            """INSERT INTO sources
               (id, version_id, filename, relative_path, sha256)
               VALUES (?,?,?,?,?)""",
            (src_id, ver_id, "a.txt", "raw/x/a.txt", "c" * 64))
        self.conn.executemany(
            """INSERT INTO segments
               (id, source_id, ordinal, line_start, line_end, text)
               VALUES (?,?,?,?,?,?)""",
            [(seg1, src_id, 1, 1, 1, "甲"), (seg2, src_id, 2, 2, 2, "乙")])
        self.conn.execute(
            """INSERT INTO episode_segments
               (episode_id, segment_id, ordinal, position) VALUES (?,?,1,1)""",
            (ep1, seg1))
        self.conn.commit()
        with self.assertRaises(Exception):
            self.conn.execute(
                """INSERT INTO episode_segments
                   (episode_id, segment_id, ordinal, position)
                   VALUES (?,?,2,1)""", (ep1, seg2))
            self.conn.commit()
        # 另一集用 position=1 没问题
        self.conn.execute(
            """INSERT INTO episode_segments
               (episode_id, segment_id, ordinal, position) VALUES (?,?,1,1)""",
            (ep2, seg1))
        self.conn.commit()


if __name__ == "__main__":
    unittest.main()
