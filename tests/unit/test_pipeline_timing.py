# -*- coding: utf-8 -*-
"""pipeline_timing 单测：临时数据根隔离（GWS_DATA_ROOT），不碰 dev/test/prod。"""
import json
import os
import tempfile
import unittest

from gws import pipeline_timing
from gws.config import load_config


class TestPipelineTiming(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_RUNNING_TESTS"] = "1"
        os.environ["GWS_ENV"] = "test"
        os.environ["GWS_DATA_ROOT"] = self._tmp.name
        self.cfg = load_config()

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("GWS_DATA_ROOT", None)

    def test_start_done_pairs_seconds(self):
        pipeline_timing.stamp("精读", "游戏甲", event="start", cfg=self.cfg)
        e = pipeline_timing.stamp("精读", "游戏甲", cfg=self.cfg)
        self.assertEqual(e["event"], "done")
        self.assertIsNotNone(e["seconds"])
        self.assertGreaterEqual(e["seconds"], 0.0)
        self.assertEqual(e["game"], "游戏甲")

    def test_done_without_start_seconds_none(self):
        e = pipeline_timing.stamp("渲染", "游戏甲",
                                  seconds=round(1.5, 1), cfg=self.cfg)
        self.assertEqual(e["seconds"], 1.5)
        # 无 start 配对时不传 seconds → None，不报错
        e2 = pipeline_timing.stamp("手写", "游戏甲", cfg=self.cfg)
        self.assertIsNone(e2["seconds"])

    def test_summary_only_done_in_order(self):
        pipeline_timing.stamp("筛窗", "游戏甲", event="start", cfg=self.cfg)
        pipeline_timing.stamp("筛窗", "游戏甲", seconds=0.2, cfg=self.cfg)
        pipeline_timing.stamp("粗判", "游戏甲", seconds=3.0,
                              note="KEEP5", cfg=self.cfg)
        entries = pipeline_timing.summary("游戏甲", cfg=self.cfg)
        self.assertEqual([x["stage"] for x in entries], ["筛窗", "粗判"])
        self.assertEqual(entries[1]["note"], "KEEP5")

    def test_games_isolated(self):
        pipeline_timing.stamp("筛窗", "游戏甲", seconds=1.0, cfg=self.cfg)
        self.assertEqual(pipeline_timing.summary("游戏乙", cfg=self.cfg), [])
        self.assertEqual(len(pipeline_timing.summary("游戏甲", cfg=self.cfg)),
                         1)

    def test_file_location_and_jsonl_format(self):
        pipeline_timing.stamp("筛窗", "游戏甲", seconds=1.0, cfg=self.cfg)
        p = pipeline_timing._path("游戏甲", self.cfg)
        self.assertTrue(str(p).startswith(self._tmp.name))
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        e = json.loads(lines[0])
        self.assertEqual(e["stage"], "筛窗")
        self.assertIn("ts", e)


if __name__ == "__main__":
    unittest.main()
