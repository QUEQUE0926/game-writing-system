# -*- coding: utf-8 -*-
"""Golden Project v0（02 §8）：端到端最小链路冒烟。

覆盖起步阶段：Import → Source → Segment（后续阶段逐步扩展
Episode → Material Card → Claim → Project）。
Golden fixture 含作者发言、NPC、ASR 噪声样本，供后续分类器回归使用。
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.ids import new_id  # noqa: E402
from gws.import_service import import_source  # noqa: E402
from gws.migrations import migrate  # noqa: E402

GOLDEN_TXT = """[作者] 这游戏的建造系统比我想的深多了。
[NPC] 欢迎来到灰烬之国，旅人。
[队友] 我先去探路，你们跟上。
【字幕】第三章：余烬
asdfqw 【ASR噪声】
[作者] 第一次进副本就被秒了，才知道要打断读条。
"""


class TestGoldenChainV0(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.cfg = load_config("test")
        self.conn = connect(self.cfg)
        migrate(self.conn)
        # 建档：Game → Version
        game_id, ver_id = new_id(), new_id()
        self.conn.execute("INSERT INTO games (id, name) VALUES (?,?)",
                          (game_id, "Golden Game"))
        self.conn.execute(
            "INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
            (ver_id, game_id, "demo"))
        self.conn.commit()
        self.ver_id = ver_id

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def test_full_chain_import_to_segment(self):
        fixture = Path(self.tmp.name) / "golden_merged.txt"
        fixture.write_text(GOLDEN_TXT, encoding="utf-8")

        result = import_source(self.cfg, self.ver_id, fixture)
        self.assertFalse(result["dedup"])
        self.assertEqual(result["segments"], 6, "非空行应逐一生成 Segment")

        # 关键内容全部落库（编码 strict、无静默丢字）
        rows = self.conn.execute(
            "SELECT text FROM segments ORDER BY ordinal").fetchall()
        joined = "\n".join(r["text"] for r in rows)
        for token in ("灰烬之国", "建造系统", "打断读条"):
            self.assertIn(token, joined)

        # 幂等：同文件重复导入去重
        again = import_source(self.cfg, self.ver_id, fixture)
        self.assertTrue(again["dedup"])

        # Raw 原文归档存在
        src = self.conn.execute("SELECT relative_path FROM sources").fetchone()
        raw_file = Path(self.cfg.data_root) / src["relative_path"]
        self.assertTrue(raw_file.exists(), "Raw 原文必须归档且可追溯")


if __name__ == "__main__":
    unittest.main()
