# -*- coding: utf-8 -*-
"""第 5 步：Episode 切集（规则轮 v0）。

规则：
- 以 Source 为单位切（同一版本多源各自成集，不混源）；
- 每集约 TARGET=50 句有效台词（speaker != unknown 或 content_type 非 noise
  均算有效；marker/header 等 noise 不计入目标长度，但照样收入集区间）；
- 切点微调：目标位置附近（±10 句）优先落在 speaker 变化的边界；
- 标题自动生成"<游戏> E<序号>"，summary 留空，作者可后续 rename；
- 幂等：源已有 episode_segments 记录则跳过；
- 少于 MIN_SEGMENTS=10 句有效台词的源跳过（如 3 句 test 文件）。

用法：
  python scripts/make_episodes.py            # 报表（只读）
  python scripts/make_episodes.py --apply    # 写库（含 audit_log）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.ids import new_id  # noqa: E402

TARGET = 50
WINDOW = 10
MIN_SEGMENTS = 10


def plan_chunks(segs: list) -> list[list]:
    """segs: 全部段（按 ordinal）。返回若干个段列表。"""
    content_idx = [i for i, s in enumerate(segs)
                   if not (s["speaker"] == "unknown"
                           and s["content_type"] in ("noise", "ui_text"))]
    if len(content_idx) < MIN_SEGMENTS:
        return []
    cuts = []  # 切在 idx 之前（idx 是新集第一段）
    start = 0
    while True:
        # 找本集内容段数达到 TARGET 的位置
        pos = None
        count = 0
        for i in range(start, len(segs)):
            if i in set(content_idx):
                count += 1
                if count >= TARGET:
                    pos = i
                    break
        if pos is None or pos >= len(segs) - 1:
            break
        # ±WINDOW 内优先 speaker 变化边界
        best = pos
        for j in range(max(pos - WINDOW, start + 1),
                       min(pos + WINDOW + 1, len(segs))):
            if segs[j]["speaker"] != segs[j - 1]["speaker"] and j not in cuts:
                best = j
                break
        cuts.append(best)
        start = best
    chunks = []
    prev = 0
    for c in cuts + [len(segs)]:
        chunks.append(segs[prev:c])
        prev = c
    return chunks


def main() -> None:
    apply = "--apply" in sys.argv
    cfg = load_config()
    conn = connect(cfg)
    try:
        sources = conn.execute("""
            SELECT s.id, g.name AS game, v.name AS ver
            FROM sources s
            JOIN game_versions v ON v.id = s.version_id
            JOIN games g ON g.id = v.game_id
            ORDER BY g.name, s.filename""").fetchall()
        print(f"=== Episode 切集报表（{'已写入' if apply else '试跑，未改库'}）"
              f" env={cfg.env}")
        for src in sources:
            done = conn.execute(
                "SELECT COUNT(*) FROM episode_segments WHERE episode_id IN "
                "(SELECT id FROM episodes WHERE version_id IN "
                "(SELECT version_id FROM sources WHERE id=?))",
                (src["id"],)).fetchone()[0]
            if done:
                print(f"--- {src['game']}: 跳过（该版本已有 {done} 条集内记录）")
                continue
            segs = conn.execute("""
                SELECT id, speaker, content_type FROM segments
                WHERE source_id=? ORDER BY ordinal""", (src["id"],)).fetchall()
            chunks = plan_chunks(segs)
            if not chunks:
                print(f"--- {src['game']} / {src['ver']}: 跳过"
                      f"（有效台词不足 {MIN_SEGMENTS} 句，{len(segs)} 段）")
                continue
            # 现有集数（同版本续编号）
            base = conn.execute("""
                SELECT COUNT(*) FROM episodes
                WHERE version_id IN (SELECT version_id FROM sources WHERE id=?)""",
                (src["id"],)).fetchone()[0]
            print(f"--- {src['game']} / {src['ver']}（{len(segs)} 段）"
                  f"→ {len(chunks)} 集")
            if apply:
                vid = conn.execute("SELECT version_id FROM sources WHERE id=?",
                                   (src["id"],)).fetchone()["version_id"]
                for n, chunk in enumerate(chunks, start=base + 1):
                    eid = new_id()
                    conn.execute(
                        """INSERT INTO episodes (id, version_id, title, summary)
                           VALUES (?,?,?,?)""",
                        (eid, vid, f"{src['game']} E{str(n).zfill(2)}", ""))
                    for pos, s in enumerate(chunk, start=1):
                        conn.execute(
                            """INSERT INTO episode_segments
                               (episode_id, segment_id, ordinal, position)
                               VALUES (?,?,?,?)""",
                            (eid, s["id"], pos, pos))
                conn.execute(
                    """INSERT INTO audit_log (id, event_name, entity_type,
                       entity_id, detail) VALUES (?,?,?,?,?)""",
                    (new_id(), "make_episodes", "source", src["id"],
                     json.dumps({"episodes": len(chunks),
                                 "sizes": [len(c) for c in chunks]},
                                ensure_ascii=False)))
            sizes = [len(c) for c in chunks]
            print(f"    各集段数: {sizes}")
        if apply:
            conn.commit()
            print("=== 已提交")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
