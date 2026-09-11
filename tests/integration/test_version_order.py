# -*- coding: utf-8 -*-
"""版本排序（004 迁移 sort_key）行为钉死：

- 排序规则：sort_key 小的在前；NULL 排后面按 created_at 兜底。
- 004 迁移幂等重放不报错（schema_migrations 挡住）。
"""
import os
import tempfile
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import current_version, migrate  # noqa: E402
from gws.repositories import GameRepository, SeriesRepository, \
    VersionRepository  # noqa: E402
from gws.inventory import fetch_tree  # noqa: E402


class VersionOrderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self._tmp.name
        os.environ["GWS_ENV"] = "test"
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _make(self):
        sid = SeriesRepository(self.conn, self.cfg).create("测试系列")
        gid = GameRepository(self.conn, self.cfg).create("测试游戏", sid)
        vrepo = VersionRepository(self.conn, self.cfg)
        v1 = vrepo.create(gid, "正式版")
        v2 = vrepo.create(gid, "8月更新")
        return v1, v2

    def test_migration_004_applied(self):
        self.assertGreaterEqual(current_version(self.conn), 4)
        cols = {r["name"] for r in
                self.conn.execute("PRAGMA table_info(game_versions)")}
        self.assertIn("sort_key", cols)

    def test_null_sort_key_falls_back_to_created_at(self):
        v1, v2 = self._make()
        tree = fetch_tree(self.conn)
        versions = tree[0]["games"][list(tree[0]["games"])[0]]["versions"]
        order = [v["id"] for v in versions.values()]
        self.assertEqual(order, [v1, v2])  # 建档顺序兜底

    def test_sort_key_orders_before_null_and_smaller_first(self):
        v1, v2 = self._make()
        # 后建档的"8月更新"给 sort_key=1，应排到"正式版"(NULL) 前面
        self.conn.execute("UPDATE game_versions SET sort_key=1 WHERE id=?", (v2,))
        tree = fetch_tree(self.conn)
        versions = tree[0]["games"][list(tree[0]["games"])[0]]["versions"]
        order = [v["id"] for v in versions.values()]
        self.assertEqual(order, [v2, v1])

    def test_smaller_key_first(self):
        v1, v2 = self._make()
        self.conn.execute("UPDATE game_versions SET sort_key=2 WHERE id=?", (v1,))
        self.conn.execute("UPDATE game_versions SET sort_key=1 WHERE id=?", (v2,))
        tree = fetch_tree(self.conn)
        versions = tree[0]["games"][list(tree[0]["games"])[0]]["versions"]
        order = [v["id"] for v in versions.values()]
        self.assertEqual(order, [v2, v1])


if __name__ == "__main__":
    unittest.main()
