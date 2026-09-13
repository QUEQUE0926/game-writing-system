# -*- coding: utf-8 -*-
"""第 7 步升级：精读入围筛选（规则粗筛 + 打分 + 窗口合并）。

与 nominate_moments.py 的关系：提名扫"值得制卡的瞬间"，本工具扫
"值得让精读模型整段读的窗口"——规则面扩展到素材卡提示词的四类目标：
① 喜欢/不满/惊讶/困惑；② 机制学习/失败/突破/观点反转；
③ 对 剧情/关卡/美术/声音/操作/性能 的具体判断；④ 疑似反转对（算法配对）。

输出：
- 报告：每游戏一份工作台（分档沿用每游戏内部相对分：高=前30%/中=次30%/低=其余，
  高价值详情首屏 20 张，噪音行不进报告）；
- JSONL：窗口原文全量导出给 AI 精读层，每行一个窗口
  （带 game/episode/source/ordinal/line 锚点、hit_kinds、score、sentences）。

用法：
  python scripts/screen_windows.py                 # 全库已分类源
  python scripts/screen_windows.py --game 银翼喵侍  # 只跑指定游戏（前缀匹配）
  python scripts/screen_windows.py --source <id>   # 只跑指定源（前缀匹配）
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.report_prune import prune_dated_reports  # noqa: E402

# ---- 规则面（对应素材卡提示词的四类目标）----
CUES_POS = re.compile(
    r"(好玩|好看|好听|舒服|爽|喜欢|爱了|推荐|真不错|真香|牛[逼Bb]?|厉害|"
    r"有点东西|绝了|值回|值得|上头|入迷)")
CUES_NEG = re.compile(
    r"(难受|恶心|劝退|弃了|退款|无聊|后悔|垃圾|太烂|不行|受不了|难玩|折磨|"
    r"痛苦|阴间|坐牢|离谱|服了|寄|烂尾|稀碎|一坨|抽象)")
CUES_SUR = re.compile(
    r"(没想到|居然|竟然|谁知道|好家伙|卧槽|我操|我去|我勒|什么鬼|不会吧|"
    r"逆天|恐怖如斯|吓死|麻了|炸了|离大谱)")
CUES_CONF = re.compile(
    r"(为什么|怎么回事|啥情况|怎么搞|搞不懂|看不懂|啥意思|什么情况|"
    r"这啥|这是啥|到底怎么)")
CUES_LEARN = re.compile(
    r"(原来[是这样如此]|懂了|明白了|学到了|终于知道|怪不得|难怪|涨知识|"
    r"窍门|方法就是|技巧)")
CUES_FAIL = re.compile(
    r"(又死了|卡关|过不去|翻车|失误|打不过|输了|失败|白给|白干|亏了|踩坑)")
JUDGE_CUES = re.compile(
    r"(优化|掉帧|卡顿|帧数|手感|判定|打击感|建模|画质|配乐|音效|配音|"
    r"剧情|关卡|难度|数值|平衡|操作|镜头|视角|翻译|本地化|引导|教程|"
    r"地图|界面|UI|性价比|体量|节奏|氛围|创意|玩法|设计|内容量|肝|氪)")
NUM_RE = re.compile(r"\d+(\.\d+)?%|\d+(\.\d+)?\s*(小时|分钟|块钱|元|GB|g)")
# 单句每类计分上限（防一段排比刷分）
# 注：反转(opinion_change)是跨句现象，单句正则实测 0 命中，已撤——
# 反转留给同集配对算法（后续 coarse/精读层做）。
WEIGHTS = {"pos": (CUES_POS, 1, 2), "neg": (CUES_NEG, 1, 2),
           "sur": (CUES_SUR, 2, 4), "conf": (CUES_CONF, 1, 2),
           "learn": (CUES_LEARN, 2, 4), "fail": (CUES_FAIL, 1, 2),
           "judge": (JUDGE_CUES, 2, 4), "num": (NUM_RE, 1, 1)}
KIND_CN = {"pos": "好评", "neg": "差评", "sur": "惊讶", "conf": "困惑",
           "learn": "学会", "fail": "失败", "judge": "判断",
           "num": "细节"}
MERGE_GAP = 6          # 命中间隔 ≤6 句并入同窗口
MERGE_NEARBY = 10      # 相邻窗口间隔 ≤10 句再合并（观点反转常隔几分钟）
CONTEXT = 20           # 窗口两侧各扩 20 句邻域（上下文恢复：反转跨句不丢）
MAX_WINDOW = 80        # 单窗口最大句数（合并+邻域后的上限参考）
MIN_SCORE = 3          # 窗口入围最低分
EP_EDGE_BONUS = 1      # 命中句落在集头/集尾 10 句内的加分
USE_HINT = {
    "rev": "反转/张力（contrasts/contradicts 优先）",
    "learn": "机制学习过程",
    "judge": "核心论据 / 机制解释",
    "sur": "开头钩子 / 标题坯",
    "pos": "氛围细节 / 好评引文",
    "neg": "反例或转折 / 差评引文",
    "conf": "困惑→理解叙事",
    "fail": "失败→突破叙事",
    "num": "玩家决策信息",
}


def sentence_hits(text: str) -> tuple[int, list[str]]:
    """单句打分。返回 (分数, 命中类别列表)。"""
    pts, kinds = 0, []
    for kind, (pat, w, cap) in WEIGHTS.items():
        n = len(pat.findall(text))
        if n:
            kinds.append(kind)
            pts += min(n * w, cap)
    return pts, kinds


def merge_windows(hits: list, n_segs: int) -> list[list]:
    """hits: [(idx, pts, kinds, seg)]。按 MERGE_GAP 合并，再扩上下文。"""
    if not hits:
        return []
    groups, cur = [], [hits[0]]
    for h in hits[1:]:
        if h[0] - cur[-1][0] <= MERGE_GAP:
            cur.append(h)
        else:
            groups.append(cur)
            cur = [h]
    groups.append(cur)
    windows = []
    for g in groups:
        # 窗口句子数 = 命中跨度 + 两侧上下文，按跨度切段保证不超 MAX_WINDOW
        span = MAX_WINDOW - 2 * CONTEXT
        cur = [g[0]]
        for h in g[1:]:
            if h[0] - cur[0][0] > span:
                windows.append((cur, max(0, cur[0][0] - CONTEXT),
                                min(n_segs, cur[-1][0] + CONTEXT + 1)))
                cur = [h]
            else:
                cur.append(h)
        windows.append((cur, max(0, cur[0][0] - CONTEXT),
                        min(n_segs, cur[-1][0] + CONTEXT + 1)))
    # 相邻窗口近距合并：观点弧线（如"不行→等等→原来很强"）不被切开
    windows.sort(key=lambda t: t[1])
    merged = [windows[0]]
    for g, lo, hi in windows[1:]:
        pg, plo, phi = merged[-1]
        if lo - phi <= MERGE_NEARBY:
            merged[-1] = (pg + g, plo, max(phi, hi))
        else:
            merged.append((g, lo, hi))
    return merged


def main() -> None:
    t0 = time.monotonic()
    game_filter = source_filter = None
    if "--game" in sys.argv:
        game_filter = sys.argv[sys.argv.index("--game") + 1]
    if "--source" in sys.argv:
        source_filter = sys.argv[sys.argv.index("--source") + 1]
    cfg = load_config()
    conn = connect(cfg)
    try:
        sources = conn.execute("""
            SELECT s.id AS sid, g.name AS game, v.name AS ver, s.filename
            FROM sources s
            JOIN game_versions v ON v.id = s.version_id
            JOIN games g ON g.id = v.game_id
            ORDER BY g.name""").fetchall()
        if game_filter:
            sources = [s for s in sources if s["game"].startswith(game_filter)]
        if source_filter:
            sources = [s for s in sources if s["sid"].startswith(source_filter)]

        windows_out = []   # JSONL 行
        for src in sources:
            segs = conn.execute("""
                SELECT id, ordinal, line_start, line_end, speaker,
                       content_type, text
                FROM segments WHERE source_id=? ORDER BY ordinal""",
                (src["sid"],)).fetchall()
            eps = conn.execute("""
                SELECT es.episode_id, es.segment_id
                FROM episode_segments es
                JOIN segments seg ON seg.id = es.segment_id
                WHERE seg.source_id=?""", (src["sid"],)).fetchall()
            ep_of = {r["segment_id"]: r["episode_id"] for r in eps}
            if not ep_of:
                continue  # 未切集的源不进窗口筛选
            # 按集组织（窗口不跨集）
            ep_segs: dict[str, list] = {}
            for s in segs:
                ep = ep_of.get(s["id"])
                if ep:
                    ep_segs.setdefault(ep, []).append(s)
            for ep_id, sl in ep_segs.items():
                ep_title = conn.execute(
                    "SELECT title FROM episodes WHERE id=?",
                    (ep_id,)).fetchone()["title"]
                usable = {s["id"] for s in sl
                          if s["speaker"] in ("author", "teammate")
                          and s["content_type"] not in ("noise",)}
                hits = []
                for i, s in enumerate(sl):
                    if s["id"] not in usable:
                        continue
                    pts, kinds = sentence_hits(s["text"])
                    if pts:
                        if i < 10 or i >= len(sl) - 10:
                            pts += EP_EDGE_BONUS
                        hits.append((i, pts, kinds, s))
                for g, lo, hi in merge_windows(hits, len(sl)):
                    wscore = sum(h[1] for h in g)
                    if wscore < MIN_SCORE:
                        continue
                    wkinds = sorted({k for h in g for k in h[2]},
                                    key=lambda k: -WEIGHTS[k][1])
                    # 密度分：每类每窗口最多计 2 次（消惊讶刷分），
                    # 再除以句数×10（消"话多红利"，r=0.68 的病根）
                    kind_cnt: dict[str, int] = {}
                    for h in g:
                        for k in h[2]:
                            kind_cnt[k] = kind_cnt.get(k, 0) + 1
                    capped = sum(min(c, 2) * WEIGHTS[k][1]
                                 for k, c in kind_cnt.items())
                    n_sents = hi - lo
                    density = round(capped / n_sents * 10, 2)
                    w = {
                        "game": src["game"], "ver": src["ver"],
                        "episode_id": ep_id,
                        "episode_title": ep_title,
                        "source_id": src["sid"],
                        "ord_start": sl[lo]["ordinal"],
                        "ord_end": sl[hi - 1]["ordinal"],
                        "line_start": sl[lo]["line_start"],
                        "line_end": sl[hi - 1]["line_end"],
                        "score": wscore,
                        "score_capped": capped,
                        "density": density,
                        "hit_kinds": wkinds,
                        "hit_reason": "、".join(
                            f"{KIND_CN[k]}x{sum(h[2].count(k) for h in g)}"
                            for k in wkinds),
                        "sentences": [
                            {"ordinal": s["ordinal"],
                             "line_start": s["line_start"],
                             "speaker": s["speaker"], "text": s["text"]}
                            for s in sl[lo:hi]],
                    }
                    w["_hits"] = list(g)  # 命中明细（报告引文用，不进 JSONL）
                    windows_out.append(w)

        # 每游戏+版本一份工作台：组内相对分档（排序用密度分，入围门槛仍是原始总分）
        by_gv: dict[tuple, list] = {}
        for w in windows_out:
            by_gv.setdefault((w["game"], w["ver"]), []).append(w)
        for gv, lst in by_gv.items():
            lst.sort(key=lambda w: -w["density"])
            n_hi = max(1, -(-len(lst) * 3 // 10))
            n_mid = -(-len(lst) * 3 // 10)
            by_gv[gv] = (lst[:n_hi], lst[n_hi:n_hi + n_mid],
                         lst[n_hi + n_mid:])

        out_dir = cfg.exports_dir / "screening"
        out_dir.mkdir(parents=True, exist_ok=True)
        today = f"{datetime.date.today():%Y%m%d}"

        # JSONL 全量导出（AI 精读层输入）
        jsonl_path = out_dir / f"windows-{today}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for w in windows_out:
                slim = {k: v for k, v in w.items() if not k.startswith("_")}
                f.write(json.dumps(slim, ensure_ascii=False) + "\n")

        HI_CAP = 20

        def quote(w, limit=2) -> list[str]:
            # 取分数最高的命中句（author/teammate），噪音行不进报告
            best = sorted(w["_hits"], key=lambda h: -h[1])[:limit]
            qs = [h[3]["text"] for h in best
                  if h[3]["speaker"] in ("author", "teammate")]
            return qs or ["（窗口内以非作者发言为主）"]

        def render(idx0, lst, detail) -> list[str]:
            out, n = [], idx0
            for w in lst:
                n += 1
                use = "、".join(USE_HINT.get(k, "待定")
                                for k in w["hit_kinds"])
                if detail:
                    out.append(f"### 窗口 {str(n).zfill(3)}｜密度 {w['density']}"
                               f"（总分 {w['score']}）｜{w['hit_reason']}")
                    out.append("")
                    for q in quote(w):
                        out.append(f"> {q}")
                    out.append("")
                    out.append(f"- 出处：{w['game']} · {w['episode_title']}"
                               f" · 第 {w['line_start']}–{w['line_end']} 行"
                               f"（{w['ord_end'] - w['ord_start'] + 1} 句）")
                    out.append(f"- 建议用途：{use}")
                    out.append("")
                else:
                    q = quote(w, 1)[0]
                    if len(q) > 70:
                        q = q[:67] + "…"
                    out.append(f"- 窗口 {str(n).zfill(3)}｜密度{w['density']}"
                               f"｜{w['hit_reason']}｜{q}"
                               f"｜{w['episode_title']} 第{w['line_start']}行")
            return out

        index = ["# 精读入围筛选 · 总索引", "",
                 f"> 生成时间：{datetime.date.today()}　环境：{cfg.env}"
                 f"　窗口总数：{len(windows_out)}",
                 f"> AI 精读输入：{jsonl_path}",
                 "> 每游戏+版本一份工作台，分档=该版本内部相对分；"
                 "窗口=命中句±5句上下文，直接可喂精读模型。", "",
                 "| 游戏 | 版本 | 高 | 中 | 低 | 最高分 |",
                 "|---|---|---|---|---|---|"]
        for game, ver in sorted(by_gv):
            hi, mid, lo = by_gv[(game, ver)]
            preview = quote(hi[0], 1)[0] if hi else ""
            if len(preview) > 36:
                preview = preview[:33] + "…"
            fname = f"{game}-{ver}-筛选-{today}.md"
            index.append(f"| {game} | [{ver}]({fname}) | {len(hi)} | "
                         f"{len(mid)} | {len(lo)} | {preview} |")

        for game, ver in sorted(by_gv):
            hi, mid, lo = by_gv[(game, ver)]
            md = [f"# {game}（{ver}）· 精读入围工作台", "",
                  f"> 高 {len(hi)}（前 {min(len(hi), HI_CAP)} 窗详情，"
                  f"其余备查）/ 中 {len(mid)} / 低 {len(lo)}", "",
                  "## ◆ 高分窗口 ｜ 优先精读", ""]
            md += render(0, hi[:HI_CAP], True) if hi else ["（本轮无）", ""]
            if len(hi) > HI_CAP:
                md += [f"### 高分窗口（备查）｜第 {HI_CAP + 1} 名起", ""]
                md += render(HI_CAP, hi[HI_CAP:], False)
            md += ["## ◇ 中分窗口 ｜ 快速扫一眼", ""]
            md += render(len(hi), mid, False) if mid else ["（本轮无）", ""]
            md += ["## · 低分窗口 ｜ 备查", ""]
            md += render(len(hi) + len(mid), lo, False) if lo \
                else ["（本轮无）", ""]
            (out_dir / f"{game}-{ver}-筛选-{today}.md").write_text(
                "\n".join(md), encoding="utf-8")

        index_path = out_dir / f"索引-{today}.md"
        index_path.write_text("\n".join(index), encoding="utf-8")
        pruned = prune_dated_reports(out_dir, ["索引-{date}.md",
                                               "*-筛选-{date}.md"], today)
        if pruned:
            print(f"清理旧报告 {len(pruned)} 份：{'、'.join(pruned)}")
        print(f"筛选完成：{len(by_gv)} 个游戏+版本，窗口 {len(windows_out)} 个"
              f"（入围门槛 {MIN_SCORE} 分）")
        print(f"报告：{index_path}")
        print(f"JSONL：{jsonl_path}")
        from gws import pipeline_timing
        e = pipeline_timing.stamp(
            "筛窗", game_filter or "_global",
            seconds=round(time.monotonic() - t0, 1),
            note=f"窗口{len(windows_out)}", cfg=cfg)
        print(f"⏱ 计时：筛窗 {e['seconds']}s 已记 {pipeline_timing._path(game_filter or '_global', cfg).name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
