# -*- coding: utf-8 -*-
"""Repository + Validation 集成测试（全部跑在临时目录）。"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import migrate  # noqa: E402
from gws.repositories import (GameRepository, SeriesRepository,  # noqa: E402
                              SourceRepository, VersionRepository)
from gws.validation import (LIFECYCLE_ERROR, REFERENCE_ERROR,  # noqa: E402
                            ValidationError)


class RepoTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.cfg and self.conn)

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def _identity(self, series: str | None = None):
        series_id = SeriesRepository(self.conn, self.cfg).create("系列") \
            if series else None
        game_id = GameRepository(self.conn, self.cfg).create("游戏", series_id)
        ver_id = VersionRepository(self.conn, self.cfg).create(game_id, "1.0")
        return series_id, game_id, ver_id


class TestCreateChain(RepoTestBase):
    def test_create_chain_with_series(self):
        series_id, game_id, ver_id = self._identity(series=True)
        self.assertIsNotNone(series_id)
        self.assertTrue(GameRepository(self.conn, self.cfg).exists(game_id))
        self.assertTrue(VersionRepository(self.conn, self.cfg).exists(ver_id))

    def test_game_requires_existing_series(self):
        with self.assertRaises(ValidationError) as ctx:
            GameRepository(self.conn, self.cfg).create("孤儿游戏", "no-such-series")
        self.assertEqual(ctx.exception.kind, REFERENCE_ERROR)

    def test_duplicate_names_rejected(self):
        _, game_id, _ = self._identity()
        with self.assertRaises(ValidationError):
            VersionRepository(self.conn, self.cfg).create(game_id, "1.0")


class TestLifecycleRules(RepoTestBase):
    def test_reference_to_trashed_series_rejected(self):
        series_id, _, _ = self._identity(series=True)
        repo = SeriesRepository(self.conn, self.cfg)
        repo.set_status(series_id, "trashed")
        with self.assertRaises(ValidationError) as ctx:
            GameRepository(self.conn, self.cfg).create("新游戏", series_id)
        self.assertEqual(ctx.exception.kind, LIFECYCLE_ERROR,
                         "trashed 对象不能接收新的正常引用")

    def test_status_flow_via_repository(self):
        _, game_id, _ = self._identity()
        repo = GameRepository(self.conn, self.cfg)
        repo.set_status(game_id, "archived")
        repo.set_status(game_id, "active")
        with self.assertRaises(ValidationError):
            repo.set_status(game_id, "bogus")


class TestPurge(RepoTestBase):
    def _source_with_segment(self):
        _, _, ver_id = self._identity()
        src = SourceRepository(self.conn, self.cfg)
        txt = Path(self.tmp.name) / "s.txt"
        txt.write_text("[作者] 测试行。\n", encoding="utf-8")
        from gws.import_service import import_source
        r = import_source(self.cfg, ver_id, txt)
        return r["source_id"]

    def test_purge_requires_confirm(self):
        src_id = self._source_with_segment()
        with self.assertRaises(ValidationError):
            SourceRepository(self.conn, self.cfg).purge(src_id, confirm=False)

    def test_purge_backs_up_and_deletes(self):
        src_id = self._source_with_segment()
        n = SourceRepository(self.conn, self.cfg).purge(src_id, confirm=True)
        self.assertGreaterEqual(n, 1, "owned-child Segment 应级联进 Trash")
        self.assertFalse(SourceRepository(self.conn, self.cfg).exists(src_id))
        backups = list((Path(self.cfg.backups_dir)).glob("purge-*"))
        self.assertEqual(len(backups), 1, "purge 前必须留备份")


if __name__ == "__main__":
    unittest.main()
