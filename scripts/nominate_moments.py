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

# ── 第二遍：有料片段（分析/对比/叙事/总结）──
# 特征词为主（不受断行影响）；文件内相对长度为辅（该源最长前10%行 +1 分）
SUBJECT_CUES = {
    "分析": re.compile(
        r"其实|本质|原因是|相当于|类似于|问题在于|核心是|设计得|机制|逻辑上|"
        r"讲究|原理|简单来说|说白了"),
    "对比": re.compile(
        r"不如|反而|前作|上一款|上一部|比之前|比原来|更像|有点像|很像|"
        r"和.{0,8}一样|跟.{0,8}一样|差多了|比.{1,6}好"),
    "叙事": re.compile(
        r"伏笔|铺垫|原来|难怪|反转|剧情|主线|任务线|这段故事|背景设定"),
    "总结": re.compile(
        r"总的来说|总体来说|总体感觉|整体来说|玩下来|玩到现在|最大问题|"
        r"最大亮点|最大的|节奏"),
}
CONTEXT = 2      # 候选前后各带几句上下文
ANALYSIS_TOP = 3  # 每集有料片段提名数
MERGE_GAP = 6     # 有料片段合并间隔
TOP_PER_EPISODE = 3  # 每集每板块提名数



def score(text: str) -> int:
    return len(CUES.findall(text))


def subject_score(text: str, len_threshold: int) -> tuple[int, list[str]]:
    """返回 (得分, 命中类型列表)。特征词每类1分；文件内相对长行 +1。"""
    kinds, pts = [], 0
    for kind, pat in SUBJECT_CUES.items():
        if pat.search(text):
            kinds.append(kind)
            pts += 1
    if len_threshold and len(text) >= len_threshold:
        pts += 1
    return pts, kinds


def _merge(hits: list, gap: int) -> list[list]:
    """相邻命中合并（间隔<=gap 句）。"""
    if not hits:
        return []
    groups, cur = [], [hits[0]]
    for h in hits[1:]:
        if h[0] - cur[-1][0] <= gap:
            cur.append(h)
        else:
            groups.append(cur)
            cur = [h]
    groups.append(cur)
    return groups


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
        lines = ["# 素材卡候选提名报告",
                 "",
                 f"> 生成时间：{datetime.date.today()}　环境：{cfg.env}",
                 "> 两遍规则扫描：①高能瞬间（情绪词）；②有料片段"
                 "（分析/对比/叙事/总结特征词 + 文件内相对长行）。",
                 "> 仅供作者挑选；挑中后按 05 提炼约定制卡"
                 "（subject=钩子坯 / quote=逐字原话 / 无判断不收卡）。",
                 ""]
        total_hi, total_sub = 0, 0
        # ── 游戏提及巡逻：花名册 = games 主名 + game_aliases ──
        roster = {}  # name -> game 显示名
        for r in conn.execute("SELECT name FROM games"):
            roster[r["name"]] = r["name"]
        for r in conn.execute("""
            SELECT ga.alias, g.name FROM game_aliases ga
            JOIN games g ON g.id = ga.game_id"""):
            roster.setdefault(r["alias"], r["name"])
        # 长名优先（避免"星际争霸"抢先吃掉"星际争霸2"）
        roster_names = sorted(roster, key=len, reverse=True)
        for ep in episodes:
            segs = conn.execute("""
                SELECT seg.id, seg.text, seg.speaker, seg.line_start
                FROM episode_segments es
                JOIN segments seg ON seg.id = es.segment_id
                WHERE es.episode_id = ? ORDER BY es.position""",
                (ep["id"],)).fetchall()
            usable = [s for s in segs
                      if s["speaker"] in ("author", "teammate")]
            if not usable:
                continue

            def emit(block_title: str, moments: list, rank_total: int):
                nonlocal lines
                out = []
                for rank, m in enumerate(moments[:rank_total], start=1):
                    i0 = max(m[0][0] - CONTEXT, 0)
                    i1 = min(m[-1][0] + CONTEXT, len(segs) - 1)
                    if block_title.startswith("高能"):
                        kinds = "情绪"
                    else:
                        kinds = "+".join(m[0][3]) or "长句"
                    out.append(
                        f"### {block_title} {rank}"
                        f"（{kinds}，强度 {m[0][2]}，"
                        f"原文第 {segs[i0]['line_start']}–"
                        f"{segs[i1]['line_start']} 行）")
                    out.append("")
                    for i in range(i0, i1 + 1):
                        s = segs[i]
                        who = {"author": "作者", "teammate": "队友"}.get(
                            s["speaker"], s["speaker"])
                        mark = " ←" if any(j[0] == i for j in m) else ""
                        out.append(f"- [{who}] {s['text']}{mark}")
                    out.append("")
                return out

            # ① 高能瞬间
            usable_ids = {s["id"] for s in usable}
            hits = [(i, s, score(s["text"]), ["情绪"]) for i, s in
                    enumerate(segs) if s["id"] in usable_ids
                    and score(s["text"]) > 0]
            hi_groups = _merge(hits, 4) if hits else []
            hi_groups.sort(key=lambda m: m[0][2], reverse=True)

            # ② 有料片段（每集自身的内容行 p90 作为相对长行阈值）
            content_lens = sorted(len(s["text"]) for s in usable)
            p90 = content_lens[int(len(content_lens) * 0.9)] if content_lens else 0
            shits = []
            for i, s in enumerate(segs):
                if s["speaker"] not in ("author", "teammate"):
                    continue
                pts, kinds = subject_score(s["text"], p90)
                if pts > 0 and score(s["text"]) == 0:  # 不与高能瞬间重复
                    shits.append((i, s, pts, kinds))
            sub_groups = _merge(shits, MERGE_GAP) if shits else []
            sub_groups.sort(key=lambda m: m[0][2], reverse=True)

            # ③ 游戏提及（花名册精确匹配；排除本集自己所在游戏名）
            mention_hits = []
            for i, s in enumerate(segs):
                if s["speaker"] not in ("author", "teammate"):
                    continue
                mentioned = {roster[n] for n in roster_names if n in s["text"]}
                mentioned.discard(ep["game"])
                if mentioned:
                    mention_hits.append((i, s, len(mentioned),
                                         sorted(mentioned)))
            mention_groups = _merge(mention_hits, MERGE_GAP) \
                if mention_hits else []
            mention_groups.sort(key=lambda m: m[0][2], reverse=True)

            if not hi_groups and not sub_groups and not mention_groups:
                continue
            lines.append(f"## {ep['game']} · {ep['title']}")
            lines.append("")
            if hi_groups:
                lines.append(f"### ◆ 高能瞬间（前 {top_n}）")
                lines.append("")
                lines += emit("高能", hi_groups, top_n)
                total_hi += min(len(hi_groups), top_n)
            if sub_groups:
                lines.append(f"### ◇ 有料片段（前 {top_n}）")
                lines.append("")
                lines += emit("有料", sub_groups, top_n)
                total_sub += min(len(sub_groups), top_n)
            if mention_groups:
                lines.append("### ◎ 游戏提及（全部）")
                lines.append("")
                for rank, m in enumerate(mention_groups, start=1):
                    games_in = sorted({g for _, _, _, gs in m for g in gs})
                    i0 = max(m[0][0] - CONTEXT, 0)
                    i1 = min(m[-1][0] + CONTEXT, len(segs) - 1)
                    lines.append(f"### 提及 {rank}（提到：{'、'.join(games_in)}，"
                                 f"原文第 {segs[i0]['line_start']}–"
                                 f"{segs[i1]['line_start']} 行）")
                    lines.append("")
                    for i in range(i0, i1 + 1):
                        s = segs[i]
                        who = {"author": "作者", "teammate": "队友"}.get(
                            s["speaker"], s["speaker"])
                        mark = " ←" if any(j[0] == i for j in m) else ""
                        lines.append(f"- [{who}] {s['text']}{mark}")
                    lines.append("")

        out = cfg.exports_dir / \
            f"moment_candidates-{datetime.date.today():%Y%m%d}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"提名完成：高能瞬间 {total_hi} + 有料片段 {total_sub} → {out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
