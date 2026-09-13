# -*- coding: utf-8 -*-
"""两段式产卡（方案一）：--from-json 的 skeletons 段只进骨架清单，
不进卡候选、不写 human_check（逐字锁照样生效）。"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")
os.environ["GWS_ENV"] = "test"

REPO = Path(__file__).resolve().parents[2]


def _load_craft():
    spec = importlib.util.spec_from_file_location(
        "craft_cards_mod", REPO / "scripts" / "craft_cards.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTwoStage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self._tmp.name
        self.out_dir = Path(self._tmp.name) / "exports" / "cards"
        self.out_dir.mkdir(parents=True)
        from gws import web_facts  # noqa
        from gws.config import load_config
        from gws.db import connect
        from gws.migrations import migrate
        self.cfg = load_config()
        conn = connect(self.cfg)
        migrate(conn)  # 建 schema（episodes 等表），ver_map 查询才能跑
        conn.close()
        self.todo = [{
            "source_id": "s1", "game": "游戏甲", "ver": "v1",
            "episode_id": "ep1", "episode_title": "游戏甲 E01",
            "line_start": 1, "line_end": 4, "density": 1.0, "score": 5,
            "sentences": [
                {"text": "这句是完整卡的原话。", "ordinal": 1,
                 "speaker": "author"},
                {"text": "这句是骨架的原话。", "ordinal": 2,
                 "speaker": "author"},
            ],
        }]
        self.items = [{
            "source_id": "s1", "episode_title": "游戏甲 E01",
            "window_line_start": 1,
            "cards": [{
                "subject": "完整卡", "detail": "d", "feeling": "f",
                "analysis": "a", "quote": "这句是完整卡的原话。",
                "help": 2, "concrete": 2, "delta": 2, "unique": 1,
                "writing": 2, "judge_reason": "j", "web_strategy": "不联网",
            }],
            "skeletons": [
                {"subject": "骨架一", "quote": "这句是骨架的原话。",
                 "why": "可能有料，先存档", "est": "低"},
            ],
        }]
        self.json_path = Path(self._tmp.name) / "in.json"
        self.json_path.write_text(json.dumps(self.items, ensure_ascii=False),
                                  encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("GWS_DATA_ROOT", None)

    def test_skeleton_routed_to_archive_not_cards(self):
        craft = _load_craft()
        craft.run_from_json(str(self.json_path), self.todo,
                            self.out_dir, "20260913", self.cfg)
        state = json.loads((self.out_dir / "cards-state-《游戏甲》-20260913.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(len(state["cards"]), 1)
        self.assertEqual(state["cards"][0]["card"]["subject"], "完整卡")
        self.assertEqual(len(state["skeletons"]), 1)
        self.assertEqual(state["skeletons"][0]["skel"]["subject"], "骨架一")
        # 草稿文件只有完整卡
        draft = (self.out_dir / "《游戏甲》素材卡草稿（default）-20260913.md") \
            .read_text(encoding="utf-8")
        self.assertIn("完整卡", draft)
        self.assertNotIn("骨架一", draft)
        # 骨架清单单独成册、含三行
        skel = (self.out_dir / "《游戏甲》素材卡骨架清单（default）-20260913.md") \
            .read_text(encoding="utf-8")
        self.assertIn("骨架一", skel)
        self.assertIn("为什么值得", skel)
        self.assertIn("未展开成卡、不进卡库", skel)

    def test_skeleton_quote_lock_enforced(self):
        craft = _load_craft()
        self.items[0]["skeletons"][0]["quote"] = "不存在的原话"
        self.json_path.write_text(json.dumps(self.items, ensure_ascii=False),
                                  encoding="utf-8")
        craft.run_from_json(str(self.json_path), self.todo,
                            self.out_dir, "20260913", self.cfg)
        state = json.loads((self.out_dir / "cards-state-《游戏甲》-20260913.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(len(state["skeletons"]), 0)
        self.assertEqual(len(state["human_check"]), 1)

    def test_no_skeletons_key_backward_compatible(self):
        craft = _load_craft()
        del self.items[0]["skeletons"]
        self.json_path.write_text(json.dumps(self.items, ensure_ascii=False),
                                  encoding="utf-8")
        craft.run_from_json(str(self.json_path), self.todo,
                            self.out_dir, "20260913", self.cfg)
        state = json.loads((self.out_dir / "cards-state-《游戏甲》-20260913.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(len(state["cards"]), 1)
        self.assertEqual(state["skeletons"], [])


if __name__ == "__main__":
    unittest.main()
