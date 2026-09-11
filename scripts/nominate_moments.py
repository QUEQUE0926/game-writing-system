# -*- coding: utf-8 -*-
"""第 7 步前置：素材卡候选提名（三遍规则扫描 + 审核工作台输出）。

扫描（零模型成本，全部规则）：
① 高能瞬间：情绪词/大笑/惊叹打分；
② 有料片段：分析/对比/叙事/总结特征词 + 文件内相对长行（每集内容行 p90）；
③ 游戏提及：花名册（games 主名 + aliases）精确匹配，排除本集自身游戏。

输出（每游戏一份审核工作台 + 索引，分档阈值按每游戏内部相对分）：
- 每游戏内部按分数排序，三档：高=本游戏前 30%（默认定制卡候选）/
  中=次 30%（默认备选）/ 低=其余（默认剔除）；阈值随游戏自适应；
- 每条只显示命中句原文（不堆上下文），带集/行号锚点与建议用途；
- 跨游戏提及候选归"话说出口的游戏"的工作台，标注"提到：某游戏"；
- 勾选即选择：把 `- [ ]` 改成 `- [x]`（或直接回复候选编号）。

用法：python scripts/nominate_moments.py [每集提名上限，默认3]
输出：data/<env>/exports/nominations/索引-<日期>.md + <游戏名>-<日期>.md
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
USE_HINT = {
    "情绪": "开场情绪 / 标题钩子坯",
    "分析": "机制论述 / 判断段",
    "对比": "跨游戏参照（reuse_value）",
    "叙事": "剧情线 / 体验过程",
    "总结": "观点收束 / 结尾",
    "提及": "跨游戏联动 / cross_references",
}
TOP_PER_EPISODE = 3   # 每集每板块提名上限
CONTEXT = 2           # （备用）上下文句数
MERGE_GAP_EMO = 4     # 高能命中合并间隔
MERGE_GAP_SUB = 6     # 有料命中合并间隔


def score(text: str) -> int:
    return len(CUES.findall(text))


def subject_score(text: str, len_threshold: int) -> tuple[int, list[str]]:
    kinds, pts = [], 0
    for kind, pat in SUBJECT_CUES.items():
        if pat.search(text):
            kinds.append(kind)
            pts += 1
    if len_threshold and len(text) >= len_threshold:
        pts += 1
    return pts, kinds


def _merge(hits: list, gap: int) -> list[list]:
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
    cfg = load_config()
    conn = connect(cfg)
    try:
        roster = {}
        for r in conn.execute("SELECT name FROM games"):
            roster[r["name"]] = r["name"]
        for r in conn.execute("""
            SELECT ga.alias, g.name FROM game_aliases ga
            JOIN games g ON g.id = ga.game_id"""):
            roster.setdefault(r["alias"], r["name"])
        roster_names = sorted(roster, key=len, reverse=True)

        episodes = conn.execute("""
            SELECT e.id, e.title, g.name AS game
            FROM episodes e
            JOIN game_versions v ON v.id = e.version_id
            JOIN games g ON g.id = v.game_id
            ORDER BY g.name, e.title""").fetchall()

        candidates = []  # dict: score, kinds, quotes, game, ep, lines
        for ep in episodes:
            segs = conn.execute("""
                SELECT seg.id, seg.text, seg.speaker, seg.line_start
                FROM episode_segments es
                JOIN segments seg ON seg.id = es.segment_id
                WHERE es.episode_id = ? ORDER BY es.position""",
                (ep["id"],)).fetchall()
            usable = [s for s in segs if s["speaker"] in ("author", "teammate")]
            if not usable:
                continue
            usable_ids = {s["id"] for s in usable}

            def add(kind_label: str, groups: list):
                for g in groups:
                    pts = sum(h[2] for h in g)
                    hits = g if len(g) <= 2 else \
                        sorted(g, key=lambda h: h[2], reverse=True)[:2]
                    quotes = [f"{h[1]['text']}（{h[1]['line_start']} 行）"
                              for h in hits]
                    candidates.append({
                        "score": pts,
                        "kinds": kind_label,
                        "quotes": quotes,
                        "game": ep["game"],
                        "ep": ep["title"],
                        "span": (min(h[1]["line_start"] for h in g),
                                 max(h[1]["line_start"] for h in g)),
                    })

            # ① 高能
            hits = [(i, s, score(s["text"]), ["情绪"]) for i, s in
                    enumerate(segs) if s["id"] in usable_ids
                    and score(s["text"]) > 0]
            groups = _merge(hits, MERGE_GAP_EMO)
            # 每集只留最强的前 TOP_PER_EPISODE 个
            groups.sort(key=lambda g: sum(h[2] for h in g), reverse=True)
            add("情绪", groups[:TOP_PER_EPISODE])

            # ② 有料（每集内容行 p90 作相对长行阈值）
            lens = sorted(len(s["text"]) for s in usable)
            p90 = lens[int(len(lens) * 0.9)] if lens else 0
            shits = []
            for i, s in enumerate(segs):
                if s["id"] not in usable_ids or score(s["text"]) > 0:
                    continue
                pts, kinds = subject_score(s["text"], p90)
                if pts > 0:
                    shits.append((i, s, pts, kinds))
            sgroups = _merge(shits, MERGE_GAP_SUB)
            sgroups.sort(key=lambda g: sum(h[2] for h in g), reverse=True)
            for g in sgroups[:TOP_PER_EPISODE]:
                pts = sum(h[2] for h in g)
                kinds = sorted({k for h in g for k in h[3]}) or ["长句"]
                hits2 = g if len(g) <= 2 else \
                    sorted(g, key=lambda h: h[2], reverse=True)[:2]
                candidates.append({
                    "score": pts,
                    "kinds": "+".join(kinds),
                    "quotes": [f"{h[1]['text']}（{h[1]['line_start']} 行）"
                               for h in hits2],
                    "game": ep["game"],
                    "ep": ep["title"],
                    "span": (min(h[1]["line_start"] for h in g),
                             max(h[1]["line_start"] for h in g)),
                })

            # ③ 游戏提及
            mhits = []
            for i, s in enumerate(segs):
                if s["id"] not in usable_ids:
                    continue
                mentioned = {roster[n] for n in roster_names if n in s["text"]}
                mentioned.discard(ep["game"])
                if mentioned:
                    mhits.append((i, s, len(mentioned), sorted(mentioned)))
            for g in _merge(mhits, MERGE_GAP_SUB):
                games_in = sorted({gm for _, _, _, gm in g for gm in gm})
                candidates.append({
                    "score": len(games_in),
                    "kinds": "提及",
                    "quotes": [
                        f"{h[1]['text']}（{h[1]['line_start']} 行）"
                        for h in g[:2]],
                    "game": ep["game"],
                    "ep": ep["title"],
                    "span": (min(h[1]["line_start"] for h in g),
                             max(h[1]["line_start"] for h in g)),
                    "games": games_in,
                })

        # 按游戏分组，每游戏内部相对分档（高=前30%，中=次30%，低=其余）
        by_game: dict[str, list] = {}
        for c in candidates:
            by_game.setdefault(c["game"], []).append(c)
        for game, lst in by_game.items():
            lst.sort(key=lambda c: c["score"], reverse=True)
            n_hi = max(1, -(-len(lst) * 3 // 10))     # ceil(n*0.3)，至少1
            n_mid = -(-len(lst) * 3 // 10)
            hi, mid = lst[:n_hi], lst[n_hi:n_hi + n_mid]
            lo = lst[n_hi + n_mid:]
            by_game[game] = (hi, mid, lo)

        def render(idx0: int, lst: list, detail: bool) -> list[str]:
            out, n = [], idx0
            for c in lst:
                n += 1
                use = "、".join(USE_HINT.get(k, "待定")
                                for k in c["kinds"].split("+"))
                extra = f"　提到：{'、'.join(c['games'])}" \
                    if c.get("games") else ""
                if detail:
                    out.append(f"### 候选 {str(n).zfill(3)}｜{c['score']} 分"
                               f"｜{c['kinds']}{extra}")
                    out.append("")
                    for q in c["quotes"]:
                        out.append(f"> {q}")
                    out.append("")
                    out.append(f"- 出处：{c['game']} · {c['ep']}"
                               f" · 原文第 {c['span'][0]}–{c['span'][1]} 行")
                    out.append(f"- 建议用途：{use}")
                    out.append("- [ ] 制卡？")
                    out.append("")
                else:
                    q = c["quotes"][0]
                    if len(q) > 80:
                        q = q[:77] + "…"
                    out.append(f"- [ ] 候选 {str(n).zfill(3)}｜{c['score']}分"
                               f"｜{c['kinds']}｜{q}"
                               f"｜{c['game']}·{c['ep']}")
            return out

        out_dir = cfg.exports_dir / "nominations"
        out_dir.mkdir(parents=True, exist_ok=True)
        today = f"{datetime.date.today():%Y%m%d}"

        index = ["# 素材卡候选提名 · 总索引", "",
                 f"> 生成时间：{datetime.date.today()}　环境：{cfg.env}"
                 f"　候选总数：{len(candidates)}",
                 "> 每个游戏一份工作台，分档按该游戏内部相对分"
                 "（高=前30% / 中=次30% / 低=其余）。",
                 "> 想写哪个游戏就开哪份工作台；勾选或回复候选编号即可。", "",
                 "| 游戏 | 高 | 中 | 低 | 最高分预览 | 跨游戏提及 |",
                 "|---|---|---|---|---|---|"]
        for game in sorted(by_game):
            hi, mid, lo = by_game[game]
            top = hi[0] if hi else (mid[0] if mid else lo[0])
            preview = top["quotes"][0]
            if len(preview) > 40:
                preview = preview[:37] + "…"
            mentions = len([c for c in hi + mid + lo if c.get("games")])
            fname = f"{game}-{today}.md"
            index.append(f"| [{game}]({fname}) | {len(hi)} | {len(mid)} | "
                         f"{len(lo)} | {preview} | {mentions} |")

        total_hi = total_mid = 0
        for game in sorted(by_game):
            hi, mid, lo = by_game[game]
            total_hi += len(hi)
            total_mid += len(mid)
            md = [f"# {game} · 审核工作台", "",
                  f"> 高 {len(hi)}（优先审核）/ 中 {len(mid)}"
                  f"（扫一眼）/ 低 {len(lo)}（默认不看）",
                  "> 勾 `- [ ]` 或回复候选编号即定制卡；"
                  "按 05 提炼约定制卡。", "",
                  "## ◆ 高价值 ｜ 优先审核", ""]
            md += render(0, hi, detail=True) if hi else ["（本轮无）", ""]
            md += ["## ◇ 中价值 ｜ 快速扫一眼", ""]
            md += render(len(hi), mid, detail=False) if mid \
                else ["（本轮无）", ""]
            md += ["## · 低价值 ｜ 备查，默认不看", ""]
            md += render(len(hi) + len(mid), lo, detail=False) if lo \
                else ["（本轮无）", ""]
            (out_dir / f"{game}-{today}.md").write_text(
                "\n".join(md), encoding="utf-8")

        (out_dir / f"索引-{today}.md").write_text(
            "\n".join(index), encoding="utf-8")
        print(f"提名完成：{len(by_game)} 个游戏，高 {total_hi} / 中 "
              f"{total_mid} / 低 {len(candidates) - total_hi - total_mid}"
              f" → {out_dir}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
