# -*- coding: utf-8 -*-
"""核验档案 web_facts：触发挂载、去重、易变条目当日拒挂。"""
import os
import tempfile
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")
os.environ["GWS_ENV"] = "test"

from gws import web_facts  # noqa: E402


class TestAutoAttach(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self._tmp.name
        self.cfg = None  # load_config 自动读 GWS_DATA_ROOT
        self.facts = [
            {"key": "medusa", "claim": "美杜莎之眼存在", "verdict": "已核实",
             "grade": "官方成就页", "conclusion": "官方成就实锤",
             "url": "https://x.test", "snippet": "获得传说道具：美杜莎之眼",
             "verified_at": "2026-09-13", "volatile": False,
             "triggers": ["美杜莎"]},
            {"key": "ea", "claim": "价格（易变）", "verdict": "已核实",
             "grade": "官方商店页", "conclusion": "¥68",
             "verified_at": "2026-09-13", "volatile": True,
             "triggers": ["抢先体验"]},
        ]

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("GWS_DATA_ROOT", None)

    def _card(self, subject="测试卡", detail=""):
        return {"subject": subject, "detail": detail, "feeling": "",
                "analysis": "", "quote": ""}

    def test_trigger_hit_attaches(self):
        web_facts.save_archive("游戏A", {"facts": self.facts,
                                         "community": []})
        c = self._card(detail="美杜莎之眼太逆天")
        n, stale = web_facts.auto_attach([c], "游戏A", "2026-09-13")
        self.assertEqual(n, 1)
        self.assertEqual(stale, [])
        self.assertEqual(c["fact_check"][0]["claim"], "美杜莎之眼存在")
        self.assertEqual(c["fact_check"][0]["date"], "2026-09-13")

    def test_no_trigger_no_attach(self):
        web_facts.save_archive("游戏A", {"facts": self.facts,
                                         "community": []})
        c = self._card(detail=" unrelated 内容 ")
        n, _ = web_facts.auto_attach([c], "游戏A", "2026-09-13")
        self.assertEqual(n, 0)
        self.assertNotIn("fact_check", c)

    def test_dedup_skips_existing_claim(self):
        web_facts.save_archive("游戏A", {"facts": self.facts,
                                         "community": []})
        c = self._card(detail="美杜莎")
        c["fact_check"] = [{"claim": "美杜莎之眼存在", "verdict": "已核实",
                            "grade": "g", "conclusion": "已有",
                            "date": "2026-09-13"}]
        n, _ = web_facts.auto_attach([c], "游戏A", "2026-09-13")
        self.assertEqual(n, 0)
        self.assertEqual(len(c["fact_check"]), 1)

    def test_volatile_stale_refused_and_reported(self):
        web_facts.save_archive("游戏A", {"facts": self.facts,
                                         "community": []})
        c = self._card(detail="抢先体验阶段")
        n, stale = web_facts.auto_attach([c], "游戏A", "2026-09-20")  # 过期
        self.assertEqual(n, 0)
        self.assertEqual(stale, [("ea", "2026-09-13")])
        self.assertNotIn("fact_check", c)

    def test_volatile_fresh_attaches(self):
        web_facts.save_archive("游戏A", {"facts": self.facts,
                                         "community": []})
        c = self._card(detail="抢先体验阶段")
        n, stale = web_facts.auto_attach([c], "游戏A", "2026-09-13")
        self.assertEqual(n, 1)
        self.assertEqual(stale, [])

    def test_missing_archive_is_noop(self):
        c = self._card(detail="美杜莎")
        n, stale = web_facts.auto_attach([c], "不存在游戏", "2026-09-13")
        self.assertEqual((n, stale), (0, []))

    def test_community_entry_shape(self):
        e = web_facts.community_entry(
            {"key": "cs01", "topic": "t", "conclusion": "c",
             "platform": "p", "url": "u", "snippet": "s",
             "date": "2026-09-13"})
        self.assertNotIn("key", e)
        self.assertEqual(e["date"], "2026-09-13")


if __name__ == "__main__":
    unittest.main()
