# -*- coding: utf-8 -*-
"""自动导入集成测试：文件名解析 + 全链路建档。"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.auto_import import auto_import, import_files, parse_stem  # noqa: E402
from gws.repositories import GameRepository  # noqa: E402
from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import migrate  # noqa: E402


class TestParseFilename(unittest.TestCase):
    def test_standard_dash(self):
        self.assertEqual(parse_stem("灰烬之国 - demo"), (None, "灰烬之国", "demo"))

    def test_double_dash(self):
        self.assertEqual(parse_stem("灰烬之国--1.0"), (None, "灰烬之国", "1.0"))

    def test_no_version_defaults(self):
        self.assertEqual(parse_stem("只有名字"), (None, "只有名字", "default"))

    def test_series_in_filename(self):
        self.assertEqual(
            parse_stem("灰烬之国 - 灰烬之国1 - 2023首次体验"),
            ("灰烬之国", "灰烬之国1", "2023首次体验"))

    def test_two_segments_always_game_version(self):
        # 两段永远是「游戏 - 版本」；系列必须用三段或文件夹表达，避免歧义
        self.assertEqual(parse_stem("纪念碑谷 - 纪念碑谷1"),
                         (None, "纪念碑谷", "纪念碑谷1"))

    def test_version_with_dash_after_series(self):
        self.assertEqual(
            parse_stem("魂系 - 只狼 - 影逝二度"),
            ("魂系", "只狼", "影逝二度"))


class TestBuildTargetName(unittest.TestCase):
    def test_with_series(self):
        from gws.auto_import import build_target_name
        self.assertEqual(
            build_target_name("灰烬之国", "灰烬之国1", "demo"),
            "灰烬之国 - 灰烬之国1 - demo.txt")

    def test_without_series(self):
        from gws.auto_import import build_target_name
        self.assertEqual(build_target_name("", "只狼", "demo"),
                         "只狼 - demo.txt")

    def test_version_defaults(self):
        from gws.auto_import import build_target_name
        self.assertEqual(build_target_name("魂系", "只狼", ""),
                         "魂系 - 只狼 - default.txt")


class TestAutoImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.conn)
        auto = Path(self.cfg.inbox_dir) / "auto"
        auto.mkdir(parents=True, exist_ok=True)
        (auto / "测试游戏A - demo.txt").write_text(
            "[作者] 甲。\n[作者] 乙。\n", encoding="utf-8")
        (auto / "测试游戏A - demo.txt").with_name(
            "测试游戏A - 1.0.txt").write_text("[作者] 丙。\n", encoding="utf-8")
        (auto / "无版本游戏.txt").write_text("[作者] 丁。\n", encoding="utf-8")

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def test_dry_run_creates_nothing(self):
        r = auto_import(self.cfg, self.conn, dry_run=True)
        self.assertTrue(r["dry_run"])
        self.assertEqual(len(r["plan"]), 3)
        n_games = self.conn.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]
        self.assertEqual(n_games, 0, "dry-run 不得真正建档")

    def test_full_auto_chain_and_reuse(self):
        r1 = auto_import(self.cfg, self.conn)
        self.assertEqual(len(r1["results"]), 3)
        games = {r["game"] for r in r1["results"]}
        self.assertEqual(games, {"测试游戏A", "无版本游戏"})
        # 同游戏两个版本 + 默认版本各一个
        n_ver = self.conn.execute(
            "SELECT COUNT(*) c FROM game_versions").fetchone()["c"]
        self.assertEqual(n_ver, 3)
        n_seg = self.conn.execute(
            "SELECT COUNT(*) c FROM segments").fetchone()["c"]
        self.assertEqual(n_seg, 4)
        # 再跑一遍：游戏/版本复用，导入去重
        r2 = auto_import(self.cfg, self.conn)
        self.assertTrue(all(x["dedup"] for x in r2["results"]))
        n_ver2 = self.conn.execute(
            "SELECT COUNT(*) c FROM game_versions").fetchone()["c"]
        self.assertEqual(n_ver2, 3, "重复运行不得新建版本")

    def test_series_subfolder_and_scoped_matching(self):
        auto = Path(self.cfg.inbox_dir) / "auto"
        for f in auto.glob("*.txt"):
            f.unlink()  # 清掉 setUp 的根目录样本，专注子文件夹场景
        s1, s2 = auto / "灰烬", auto / "灰烬之国"
        s1.mkdir(exist_ok=True)
        s2.mkdir(exist_ok=True)
        # 同名游戏放在两个不同系列下 → 必须是两个独立档案
        (s1 / "灰烬之国1 - demo.txt").write_text("[作者] s1。\n", encoding="utf-8")
        (s2 / "灰烬之国1 - demo.txt").write_text("[作者] s2。\n", encoding="utf-8")
        r = auto_import(self.cfg, self.conn)
        self.assertEqual(len(r["results"]), 2)
        n_games = self.conn.execute(
            "SELECT COUNT(*) c FROM games").fetchone()["c"]
        self.assertEqual(n_games, 2, "跨系列同名游戏不得混档")
        n_series = self.conn.execute(
            "SELECT COUNT(*) c FROM series").fetchone()["c"]
        self.assertEqual(n_series, 2)
        for row in self.conn.execute(
                "SELECT series_id, name FROM games"):
            self.assertIsNotNone(row["series_id"])

    def test_alias_matching_within_series(self):
        auto_root = Path(self.cfg.inbox_dir) / 'auto'
        for f in auto_root.glob('*.txt'):
            f.unlink()
        from gws.repositories import GameRepository
        auto = Path(self.cfg.inbox_dir) / "auto"
        s = auto / "灰烬之国"
        s.mkdir(parents=True, exist_ok=True)
        (s / "灰烬之国1 - demo.txt").write_text("[作者] 甲。\n", encoding="utf-8")
        auto_import(self.cfg, self.conn)
        # 给游戏加英文名别名
        game_id = self.conn.execute(
            "SELECT id FROM games LIMIT 1").fetchone()["id"]
        GameRepository(self.conn, self.cfg).add_alias(game_id, "Cinderia")
        # 用英文名文件名再导入 → 应匹配到同一游戏、只新建版本
        (s / "Cinderia - 1.0.txt").write_text("[作者] 乙。\n", encoding="utf-8")
        r = auto_import(self.cfg, self.conn)
        target = [x for x in r["results"] if x["file"] == "Cinderia - 1.0.txt"][0]
        self.assertEqual(target["game_id"], game_id, "别名应匹配到同一游戏")
        n_games = self.conn.execute(
            "SELECT COUNT(*) c FROM games").fetchone()["c"]
        self.assertEqual(n_games, 1, "别名不得新建游戏档案")

    def test_add_alias_conflict_rejected(self):
        from gws.repositories import (GameRepository, SeriesRepository,
                                      VersionRepository)
        cfg, conn = self.cfg, self.conn
        sr = SeriesRepository(conn, cfg)
        s1 = sr.create("系列一")
        s2 = sr.create("系列二")
        g1 = GameRepository(conn, cfg).create("游戏A", s1)
        g2 = GameRepository(conn, cfg).create("游戏A", s2)
        gr = GameRepository(conn, cfg)
        gr.add_alias(g1, "Common")
        with self.assertRaises(Exception):
            gr.add_alias(g2, "Common")  # 别名全局唯一，不得指向两个游戏

    def test_rename_keeps_data(self):
        auto_root = Path(self.cfg.inbox_dir) / 'auto'
        for f in auto_root.glob('*.txt'):
            f.unlink()
        from gws.repositories import GameRepository
        auto = Path(self.cfg.inbox_dir) / "auto"
        (auto / "旧名 - demo.txt").write_text("[作者] 行。\n", encoding="utf-8")
        auto_import(self.cfg, self.conn)
        gr = GameRepository(self.conn, self.cfg)
        game_id = self.conn.execute(
            "SELECT id FROM games WHERE name='旧名'").fetchone()["id"]
        gr.rename(game_id, "新名")
        row = self.conn.execute(
            "SELECT name FROM games WHERE id=?", (game_id,)).fetchone()
        self.assertEqual(row["name"], "新名")
        # 版本和 Segment 都还在
        n_ver = self.conn.execute(
            "SELECT COUNT(*) c FROM game_versions").fetchone()["c"]
        n_seg = self.conn.execute(
            "SELECT COUNT(*) c FROM segments").fetchone()["c"]
        self.assertEqual((n_ver, n_seg), (1, 1))
        # 改名后旧名字自动成为别名：旧名字的 txt 仍匹配到同一档案
        # （该游戏属于默认系列"旧名"，须在系列内匹配）
        series_row = self.conn.execute(
            "SELECT s.id FROM series s JOIN games g ON g.series_id=s.id "
            "WHERE g.id=?", (game_id,)).fetchone()
        self.assertEqual(
            gr.find_by_name_or_alias("旧名", series_row["id"]), game_id)
        (auto / "旧名 - 1.0.txt").write_text("[作者] 又一行。\n",
                                             encoding="utf-8")
        r = auto_import(self.cfg, self.conn)
        target = [x for x in r["results"]
                  if x["file"] == "旧名 - 1.0.txt"][0]
        self.assertEqual(target["game_id"], game_id,
                         "改名后旧名字文件不得新建档案")


if __name__ == "__main__":
    unittest.main()


class TestDefaultSeriesResolution(unittest.TestCase):
    """默认系列（系列=游戏名）下的匹配与改名同步（自测发现的问题回归）。"""

    def setUp(self):
        self._old_root = os.environ.get("GWS_DATA_ROOT")
        self.tmp = tempfile.mkdtemp()
        os.environ["GWS_DATA_ROOT"] = self.tmp
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.conn)
        self.dir = Path(self.tmp)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._old_root:
            os.environ["GWS_DATA_ROOT"] = self._old_root

    def test_rename_syncs_default_series_and_alias_rematch(self):
        (self.dir / "Cinderia - demo.txt").write_text(
            "[作者] 一。\n", encoding="utf-8")
        (self.dir / "Cinderia - v2.txt").write_text(
            "[作者] 二。\n", encoding="utf-8")
        r1 = import_files(self.cfg, self.conn, [str(self.dir / "Cinderia - demo.txt")])
        gid = r1["results"][0]["game_id"]
        GameRepository(self.conn, self.cfg).rename(gid, "灰烬之国")
        sname = self.conn.execute(
            "SELECT s.name FROM series s JOIN games g ON g.series_id=s.id "
            "WHERE g.id=?", (gid,)).fetchone()[0]
        self.assertEqual(sname, "灰烬之国", "默认系列名应随游戏改名")
        r2 = import_files(self.cfg, self.conn,
                          [str(self.dir / "Cinderia - v2.txt")])
        x = r2["results"][0]
        self.assertEqual(x["game_id"], gid, "旧英文名应经别名归到同一档案")
        self.assertEqual(x["game"], "灰烬之国")
        self.assertEqual(x["version"], "v2")
        n = self.conn.execute("SELECT COUNT(*) c FROM games").fetchone()[0]
        self.assertEqual(n, 1, "不得新建档案")

    def test_ambiguous_name_requires_explicit_series(self):
        gr = GameRepository(self.conn, self.cfg)
        gr.create("灰烬之国II")
        from gws.repositories import SeriesRepository
        s2 = SeriesRepository(self.conn, self.cfg).create("别的系列")
        gr.create("灰烬之国II", s2)
        f = self.dir / "灰烬之国II - demo.txt"
        f.write_text("[作者] 歧义。\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_files(self.cfg, self.conn, [str(f)])


class TestTakeCounter(unittest.TestCase):
    """同游戏同版本多实况：文件名 "#N" 序号剥离归同一版本。"""

    def setUp(self):
        self._old_root = os.environ.get("GWS_DATA_ROOT")
        self.tmp = tempfile.mkdtemp()
        os.environ["GWS_DATA_ROOT"] = self.tmp
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.conn)
        self.dir = Path(self.tmp)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._old_root:
            os.environ["GWS_DATA_ROOT"] = self._old_root

    def test_hash_counter_strips_to_same_version(self):
        self.assertEqual(parse_stem("灰烬之国 - demo #2"),
                         (None, "灰烬之国", "demo"))
        self.assertEqual(parse_stem("魂系 - 只狼 - demo #3"),
                         ("魂系", "只狼", "demo"))
        self.assertEqual(parse_stem("无序号 - v1"), (None, "无序号", "v1"))

    def test_multiple_takes_import_same_version(self):
        for n, name in enumerate(
                ["灰烬之国 - demo.txt", "灰烬之国 - demo #2.txt",
                 "灰烬之国 - demo #3.txt"], start=1):
            (self.dir / name).write_text(f"[作者] 实况{n}。\n",
                                         encoding="utf-8")
        r = import_files(self.cfg, self.conn, [
            str(self.dir / n) for n in
            ["灰烬之国 - demo.txt", "灰烬之国 - demo #2.txt",
             "灰烬之国 - demo #3.txt"]])
        versions = {x["version"] for x in r["results"]}
        game_ids = {x["game_id"] for x in r["results"]}
        self.assertEqual(versions, {"demo"}, "三个实况应同归 demo 版本")
        self.assertEqual(len(game_ids), 1, "应同一游戏档案")
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) c FROM sources").fetchone()[0], 3,
            "同版本下应有 3 个 Source")

    def test_build_target_name_with_take(self):
        from gws.auto_import import build_target_name
        self.assertEqual(
            build_target_name("灰烬之国", "灰烬之国1", "demo", take=2),
            "灰烬之国 - 灰烬之国1 - demo #2.txt")
        self.assertEqual(
            build_target_name("灰烬之国", "灰烬之国1", "demo"),
            "灰烬之国 - 灰烬之国1 - demo.txt")
