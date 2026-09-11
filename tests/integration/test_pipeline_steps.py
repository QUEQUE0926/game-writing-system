# -*- coding: utf-8 -*-
"""第 4/5 步规则轮的验收固化（Golden 样式）。

钉死两件事：
1. classify_speakers：diarized/solo 两种模式的关键行为（标签→noise、
   正文归映射说话人、solo 默认 author、UI 模式→ui）；
2. make_episodes.plan_chunks：切集守恒（内容段总数不变）与
   每集有效台词上限。

脚本模块按路径加载（scripts/ 目录会遮蔽 gws 包名，见 HANDOFF 坑3）。
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.ids import new_id  # noqa: E402
from gws.migrations import migrate  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestClassifySpeakers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.conn = connect(load_config("test"))
        migrate(self.conn)
        self.mod = _load("classify_speakers")
        c = self.conn
        self.game_id, self.ver_id = new_id(), new_id()
        c.execute("INSERT INTO games (id, name) VALUES (?,?)",
                  (self.game_id, "测试游戏"))
        c.execute("INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
                  (self.ver_id, self.game_id, "1.0"))

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def _seed_source(self, texts: list[str]) -> str:
        src_id = new_id()
        self.conn.execute(
            """INSERT INTO sources
               (id, version_id, filename, relative_path, sha256)
               VALUES (?,?,?,?,?)""",
            (src_id, self.ver_id, "a.txt", "raw/x/a.txt", "d" * 64))
        for i, t in enumerate(texts, start=1):
            self.conn.execute(
                """INSERT INTO segments
                   (id, source_id, ordinal, line_start, line_end, text)
                   VALUES (?,?,?,?,?,?)""",
                (new_id(), src_id, i, i, i, t))
        self.conn.commit()
        return src_id

    def _speaker_of(self, src_id):
        return {r["text"]: r["speaker"] for r in self.conn.execute(
            "SELECT text, speaker FROM segments WHERE source_id=?",
            (src_id,))}

    def test_diarized_mode(self):
        src = self._seed_source([
            "测试游戏_原文",       # 标题头 → noise（speaker 留 unknown）
            "发言人1",             # 标签 → noise
            "大家好，开始玩。",     # → author
            "发言人2",
            "对对对。",            # → teammate
        ])
        self.mod.classify(self.conn, apply=True)
        spk = self._speaker_of(src)
        self.assertEqual(spk["大家好，开始玩。"], "author")
        self.assertEqual(spk["对对对。"], "teammate")
        for marker in ("测试游戏_原文", "发言人1", "发言人2"):
            self.assertEqual(spk[marker], "unknown")

    def test_solo_mode(self):
        src = self._seed_source([
            "测试游戏_原文",
            "好的，我们现在来玩这款游戏。",
            "【任务完成】",        # UI 模式 → ui
            "警告，敌袭。",         # UI 模式 → ui
        ])
        self.mod.classify(self.conn, apply=True)
        spk = self._speaker_of(src)
        self.assertEqual(spk["好的，我们现在来玩这款游戏。"], "author")
        self.assertEqual(spk["【任务完成】"], "ui")
        self.assertEqual(spk["警告，敌袭。"], "ui")

    def test_override_map_game_audio(self):
        """按文件映射修正：星际争霸2 的发言人2 → game_audio。"""
        c = self.conn
        game2, ver2 = new_id(), new_id()
        c.execute("INSERT INTO games (id, name) VALUES (?,?)",
                  (game2, "星际争霸2"))
        c.execute("INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
                  (ver2, game2, "1.0"))
        src_id = new_id()
        c.execute(
            """INSERT INTO sources
               (id, version_id, filename, relative_path, sha256)
               VALUES (?,?,?,?,?)""",
            (src_id, ver2, "s.txt", "raw/x/s.txt", "e" * 64))
        for i, t in enumerate(["发言人1", "开始教学。", "发言人2",
                               "你的盟友基地遭到攻击。"], start=1):
            c.execute(
                """INSERT INTO segments
                   (id, source_id, ordinal, line_start, line_end, text)
                   VALUES (?,?,?,?,?,?)""",
                (new_id(), src_id, i, i, i, t))
        c.commit()
        self.mod.classify(self.conn, apply=True)
        spk = self._speaker_of(src_id)
        self.assertEqual(spk["开始教学。"], "author")
        self.assertEqual(spk["你的盟友基地遭到攻击。"], "game_audio")

    def test_idempotent_never_reclassifies(self):
        """已有 speaker 的段不被重跑覆盖。"""
        src = self._seed_source(["好的，开始。"])
        self.mod.classify(self.conn, apply=True)
        self.conn.execute(
            "UPDATE segments SET speaker='teammate' WHERE source_id=?",
            (src,))
        self.conn.commit()
        self.mod.classify(self.conn, apply=True)
        self.assertEqual(self._speaker_of(src)["好的，开始。"], "teammate")


class TestPlanChunks(unittest.TestCase):
    def setUp(self):
        self.plan = _load("make_episodes").plan_chunks

    @staticmethod
    def _segs(n, speaker="author", noise_every=0):
        segs = []
        for i in range(n):
            if noise_every and i % noise_every == 0:
                segs.append({"id": str(i), "speaker": "unknown",
                             "content_type": "noise"})
            else:
                segs.append({"id": str(i), "speaker": speaker,
                             "content_type": "dialogue"})
        return segs

    def test_chunking_preserves_all_segments(self):
        segs = self._segs(120)
        chunks = self.plan(segs)
        self.assertEqual(sum(len(c) for c in chunks), len(segs))

    def test_content_per_chunk_bounded(self):
        segs = self._segs(300)
        chunks = self.plan(segs)
        for chunk in chunks[:-1]:
            content = sum(1 for s in chunk if s["content_type"] != "noise")
            self.assertLessEqual(content, 60)  # TARGET(50) + WINDOW(10)

    def test_too_few_segments_skipped(self):
        self.assertEqual(self.plan(self._segs(5)), [])
        self.assertEqual(self.plan([]), [])

    def test_noise_only_not_counted(self):
        """纯 noise 段不计入目标长度，但仍被收入某个集。"""
        segs = self._segs(130, noise_every=2)
        chunks = self.plan(segs)
        self.assertEqual(sum(len(c) for c in chunks), 130)

    def test_boundary_prefers_speaker_change(self):
        """切点 ±10 内优先落在说话人变化处。"""
        segs = [{"id": str(i), "speaker": "author", "content_type": "dialogue"}
                for i in range(50)]
        segs += [{"id": str(50 + i), "speaker": "teammate",
                  "content_type": "dialogue"} for i in range(100)]
        chunks = self.plan(segs)
        # 第一刀应恰好在 speaker 从 author→teammate 的边界（idx 50）
        self.assertEqual(len(chunks[0]), 50)
        self.assertEqual(chunks[1][0]["speaker"], "teammate")


if __name__ == "__main__":
    unittest.main()
