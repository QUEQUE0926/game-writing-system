# -*- coding: utf-8 -*-
"""import_cards.py 写库器集成测试（隔离临时库，不碰 dev/test/prod）。

链路：建库 → 直接 SQL 建最小档案（系列/游戏/版本/源/3句segment/集绑定）→
伪造 cards-state → 写库 → 验证 material_cards / material_card_evidence /
audit_log / 幂等 / 无锚点拒绝。
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["GWS_RUNNING_TESTS"] = "1"
os.environ["GWS_DATA_ROOT"] = tempfile.mkdtemp()

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.ids import new_id  # noqa: E402
from gws.migrations import migrate  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "import_cards", ROOT / "scripts" / "import_cards.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(argv: list[str]):
    ic = _load_script()
    old = sys.argv
    sys.argv = ["import_cards.py"] + argv
    try:
        ic.main()
    finally:
        sys.argv = old


class TestImportCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()
        (cls.cfg.exports_dir / "cards").mkdir(parents=True, exist_ok=True)
        conn = connect(cls.cfg)
        migrate(conn)
        cls.conn = conn
        ids = {t: new_id() for t in ("series", "game", "ver", "src", "ep")}
        cls.ids = ids
        conn.execute("INSERT INTO series (id, name) VALUES (?, 'S')",
                     (ids["series"],))
        conn.execute("INSERT INTO games (id, series_id, name) VALUES (?,?, 'G')",
                     (ids["game"], ids["series"]))
        conn.execute("INSERT INTO game_versions (id, game_id, name)"
                     " VALUES (?,?,'v1')", (ids["ver"], ids["game"]))
        conn.execute("INSERT INTO sources (id, version_id, filename,"
                     " relative_path, source_type, sha256, encoding)"
                     " VALUES (?,?, 'f.txt','f.txt','single_txt','x','utf-8')",
                     (ids["src"], ids["ver"]))
        conn.execute(
            "INSERT INTO episodes (id, version_id, title) VALUES (?,?,'E01')",
            (ids["ep"], ids["ver"]))
        for i, text in enumerate(("第一句原话在这里。", "第二句。", "第三句。"), 1):
            sid = new_id()
            conn.execute(
                "INSERT INTO segments (id, source_id, ordinal, line_start,"
                " line_end, text) VALUES (?,?,?,?,?,?)",
                (sid, ids["src"], i, i, i, text))
            conn.execute(
                "INSERT INTO episode_segments"
                " (episode_id, segment_id, ordinal, position)"
                " VALUES (?,?,?,?)", (ids["ep"], sid, i, i))
        conn.commit()

    def _state_file(self, name: str, quote: str) -> Path:
        state = {"cards": [{
            "card": {"subject": "测试卡", "detail": "细节", "feeling": "感受",
                     "analysis": "分析", "judge_reason": "判断",
                     "quote": quote, "concrete": 2, "writing": 3,
                     "help": 1, "unique": 2},
            "window": {"episode_id": self.ids["ep"], "line_start": 1,
                       "line_end": 3}}], "human_check": []}
        f = self.cfg.exports_dir / "cards" / f"cards-state-{name}.json"
        f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return f

    def test_10_dry_run_writes_nothing(self):
        f = self._state_file("t1", "第一句原话在这里。")
        _run(["--file", str(f)])
        n = self.conn.execute(
            "SELECT COUNT(*) FROM material_cards").fetchone()[0]
        self.assertEqual(n, 0, "dry-run 不应写库")

    def test_20_apply_and_idempotent(self):
        f = self._state_file("t2", "第一句原话在这里。")
        _run(["--file", str(f), "--apply"])
        row = self.conn.execute("SELECT * FROM material_cards").fetchone()
        self.assertEqual(row["subject"], "测试卡")
        self.assertEqual(row["observation"], "细节")
        self.assertEqual(row["experience"], "感受")
        self.assertEqual(row["interpretation"], "分析")
        self.assertEqual(row["judgement"], "判断")
        self.assertEqual(row["quote"], "第一句原话在这里。")
        self.assertEqual(row["evidence_strength"], 2)
        self.assertEqual(row["writing_value"], 3)
        self.assertEqual(row["author_interest"], 1)
        self.assertEqual(row["reuse_value"], 2)
        self.assertEqual(row["status"], "active")
        seg1 = self.conn.execute(
            "SELECT id FROM segments WHERE line_start=1").fetchone()["id"]
        ev = self.conn.execute(
            "SELECT segment_id FROM material_card_evidence").fetchall()
        self.assertEqual([e["segment_id"] for e in ev], [seg1])
        audit = self.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_name="
            "'import_cards'").fetchone()[0]
        self.assertEqual(audit, 1)
        _run(["--file", str(f), "--apply"])   # 幂等重跑
        n = self.conn.execute(
            "SELECT COUNT(*) FROM material_cards").fetchone()[0]
        self.assertEqual(n, 1, "同 quote+episode 重复导入应跳过")

    def test_30_no_anchor_rejected(self):
        f = self._state_file("t3", "原文里根本没有这句话")
        _run(["--file", str(f), "--apply"])
        n = self.conn.execute(
            "SELECT COUNT(*) FROM material_cards").fetchone()[0]
        self.assertEqual(n, 1, "无锚点卡应被拒绝，库中仍是 1 张")


if __name__ == "__main__":
    unittest.main()
