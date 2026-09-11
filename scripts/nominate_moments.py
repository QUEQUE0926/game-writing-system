# -*- coding: utf-8 -*-
"""第 7 步前置：素材卡候选瞬间提名（规则轮，零成本、只读）。

从每集里按"情绪密度"语言特征打分，聚成候选瞬间，导出提名报告
（Markdown，含上下文与行号锚点），供作者挑选后制成素材卡。

约定（05_MATERIAL_CARD_SYSTEM 提炼约定）：
- AI 只提名，不代笔；作者挑选/改写后才建卡。

打分特征（高能语言信号）：
- 情绪词/粗口强化：卧槽/我操/我去/离谱/服了/笑死/好家伙/绝了/寄/抽象…
- 大笑：哈哈哈(3+)、233、笑尿
- 惊叹/反问：居然/竟然/不会吧/什么鬼/???/！！

用法：
  python scripts/nominate_moments.py [每集提名数，默认3]
输出：data/<env>/exports/moment_candidates-<日期>.md
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402

CUES = re.compile(
    r"(卧槽|我操|我去|我勒|离谱|服了|笑死|好家伙|绝了|抽象|牛逼|NB|恐怖如斯|"
    r"寄|吓死|麻了|炸了|逆天|变态|恶心|离大谱|什么鬼|不会吧|居然|竟然|"
    r"哈哈哈+|233+|笑尿|爽|舒服了)")
TOP_PER_EPISODE = 3
CONTEXT = 2  # 候选前后各带几句上下文


def score(text: str) -> int:
    hits = CUES.findall(text)
    return len(hits)


def main() -> None:
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() \
        else TOP_PER_EPISODE
    cfg = load_config()
    conn = connect(cfg)
    try:
        episodes = conn.execute("""
            SELECT e.id, e.title, g.name AS game
            FROM episodes e
            JOIN game_versions v ON v.id = e.version_id
            JOIN games g ON g.id = v.game_id
            ORDER BY g.name, e.title""").fetchall()
        lines = ["# 素材卡候选瞬间提名报告",
                 "",
                 f"> 生成时间：{datetime.date.today()}　环境：{cfg.env}",
                 "> 仅供作者挑选；挑中后按 05 提炼约定制卡"
                 "（subject=钩子坯 / quote=逐字原话 / 无判断不收卡）。",
                 ""]
        total = 0
        for ep in episodes:
            segs = conn.execute("""
                SELECT seg.id, seg.text, seg.speaker, seg.line_start
                FROM episode_segments es
                JOIN segments seg ON seg.id = es.segment_id
                WHERE es.episode_id = ? ORDER BY es.position""",
                (ep["id"],)).fetchall()
            scored = [(i, s, score(s["text"])) for i, s in enumerate(segs)]
            hits = [(i, s, k) for i, s, k in scored if k > 0
                    and s["speaker"] in ("author", "teammate")]
            if not hits:
                continue
            # 合并相邻命中成瞬间（间隔<=4句算同一瞬间），瞬间得分求和
            moments = []
            cur = [hits[0]]
            for h in hits[1:]:
                if h[0] - cur[-1][0] <= 4:
                    cur.append(h)
                else:
                    moments.append(cur)
                    cur = [h]
            moments.append(cur)
            moments.sort(key=lambda m: sum(k for _, _, k in m), reverse=True)
            lines.append(f"## {ep['game']} · {ep['title']}")
            lines.append("")
            for rank, m in enumerate(moments[:top_n], start=1):
                total += 1
                i0, i1 = max(m[0][0] - CONTEXT, 0), \
                    min(m[-1][0] + CONTEXT, len(segs) - 1)
                lines.append(f"### 候选 {rank}（强度 "
                             f"{sum(k for _, _, k in m)}，"
                             f"原文第 {segs[i0]['line_start']}–"
                             f"{segs[i1]['line_start']} 行）")
                lines.append("")
                for i in range(i0, i1 + 1):
                    s = segs[i]
                    who = {"author": "作者", "teammate": "队友"}.get(
                        s["speaker"], s["speaker"])
                    mark = " ←" if any(j == i for j, _, _ in m) else ""
                    lines.append(f"- [{who}] {s['text']}{mark}")
                lines.append("")
        out = cfg.exports_dir / \
            f"moment_candidates-{datetime.date.today():%Y%m%d}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"提名完成：{total} 个候选瞬间 → {out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
