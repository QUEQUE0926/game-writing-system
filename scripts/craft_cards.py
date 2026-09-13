# -*- coding: utf-8 -*-
"""第 7 步主体：精读产卡（第三层）——读精读名单，产出素材卡草稿。

输入：exports/screening/readlist-<日期>.jsonl（coarse_gate.py 产出，默认最新）
产出：
- 卡片草稿 卡片草稿-<日期>.md（按用户素材卡提示词的格式，进"待人工审核"）；
- human_check-<日期>.md（程序锁不过、需要人工回查的条目）；
- cards-state-<日期>.json（原始卡 JSON，供后续打分/关联用）。

程序锁（模型无权填的字段）：
- 证据位置：程序从窗口锚点直接带出（游戏/集/行号）；
- 原话逐字锁：卡里的"玩家原话"必须在窗口原文中逐字存在（去空白比对），
  不过 → 带错误重试一次 → 再不过 → 卡作废，进 human_check，绝不入库展示为合格卡。

模型可配置（环境变量优先）：
  GWS_LLM_URL   默认 http://localhost:11434（Ollama 兼容口）
  GWS_LLM_MODEL 默认本地 qwen3:4b-instruct-2507-q4_K_M（链路测试替身）
  正式跑换联网强模型：GWS_LLM_URL=<api地址> GWS_LLM_MODEL=<模型名> 即可，
  要求 /api/generate 兼容（Ollama 口）；不兼容口后续再加适配。

用法：
  python scripts/craft_cards.py --limit 3    # 小批量测试（调 LLM）
  python scripts/craft_cards.py              # 全量精读名单
  python scripts/craft_cards.py --from-json cards.json
        # 人工/AI 直接产卡模式：cards.json = [{"window_line_start": 1,
        #   "episode_title": "...", "cards":[{subject,detail,feeling,
        #   analysis,tension?,tension_type?,quote}]}, ...]
        # 同样过逐字锁与渲染（谁写卡都逃不掉程序锁）
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402

LLM_URL = os.environ.get("GWS_LLM_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("GWS_LLM_MODEL",
                           "qwen3:4b-instruct-2507-q4_K_M")
SEED = 42

CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "detail": {"type": "string"},
                    "feeling": {"type": "string"},
                    "analysis": {"type": "string"},
                    "tension": {"type": "string"},
                    "tension_type": {"type": "string",
                                     "enum": ["反预期", "价值观冲突",
                                              "与常识相反", "自我反转", ""]},
                    "quote": {"type": "string"},
                },
                "required": ["subject", "detail", "feeling", "analysis",
                             "quote"],
            },
        }
    },
    "required": ["cards"],
}
PROMPT = """你是游戏实况素材卡提炼员。从下面的转录片段（含转写错别字）中
只提取可能影响评测结论的内容，输出 JSON（cards 数组，没有值得提取的就给空数组）。

重点寻找：
1. 玩家明确的喜欢、不满、惊讶、困惑；
2. 机制学习、失败、突破和观点变化；
3. 对剧情、关卡、美术、声音、操作、性能的具体判断；
4. 能代表体验的原话。

硬性规则：
- quote 必须从下面的转录里【逐字复制】，不改一个字、不补全省略；
- detail 必须具体（数字、例子、操作），不许只留抽象结论；
- feeling 写玩家当时的感受+判断，analysis 按"体验→设计/原因→观点"写，
  证据不足就写"暂不能形成观点"；
- tension（张力）只在真的有反直觉/想争辩的点时写，没有就空着，禁止硬凑；
- 一段通常 0~3 张卡，宁缺毋滥。

转录内容（第 {ls}–{le} 行）：
{text}"""


def ask_llm(prompt: str) -> dict:
    body = json.dumps({
        "model": LLM_MODEL, "stream": False, "seed": SEED,
        "keep_alive": "15m", "format": CARD_SCHEMA, "prompt": prompt,
        "options": {"temperature": 0.4, "num_predict": 2000},
    }).encode()
    req = urllib.request.Request(LLM_URL + "/api/generate", body,
                                 {"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=600)
    return json.loads(json.loads(r.read())["response"])


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def quote_ok(quote: str, window: dict) -> bool:
    """原话逐字锁：去空白后必须在窗口原文中出现。"""
    if not quote or not norm(quote) in norm(
            "".join(s["text"] for s in window["sentences"])):
        return False
    return True


# 联网字段新规矩（05 文档 2026-09-13 修订）：fact_check / community_scan 结构化，
# 每条三件套=结论（含等级措辞）+链接+来源页逐字原文片段。
# 判定等级措辞冻结在 05 文档；反证/无信号/无法验证必须进 human_check。
HC_VERDICTS = ("存疑", "无信号", "无法验证")


def _web_entry_lines(tag: str, e: dict) -> list[str]:
    head = f"  - **{tag}**：{e.get('claim') or e.get('topic', '')}"
    if e.get("verdict"):
        head += f"｜{e['verdict']}"
    lines = [head]
    if e.get("conclusion"):
        lines.append(f"    结论：{e['conclusion']}")
    grade = e.get("grade") or e.get("platform") or ""
    if grade:
        lines.append(f"    来源层级：{grade}")
    if e.get("url"):
        lines.append(f"    链接：{e['url']}")
    if e.get("snippet"):
        lines.append(f"    原文片段：「{e['snippet']}」")
    if e.get("date"):
        lines.append(f"    核验日期：{e['date']}")
    return lines


def render_web_block(c: dict) -> list[str]:
    """渲染「核对（事实核验）」+「社区参照」两栏；旧自由文本字段兜底兼容。"""
    fc = c.get("fact_check") or []
    cs = c.get("community_scan") or []
    out: list[str] = []
    if fc:
        out.append("- **核对（事实核验）**：")
        for e in fc:
            out += _web_entry_lines("条目", e)
    if cs:
        out.append("- **社区参照（非事实依据）**：")
        for e in cs:
            out += _web_entry_lines("条目", e)
    if not fc and not cs:
        legacy = c.get("ai_web") or c.get("web_check")
        out.append("- **AI辅助结论（联网）**："
                   + (legacy or "无外部核验项——本卡信息全部来自转录原文（玩家口述）"))
        if c.get("web_check") and c.get("ai_web"):
            out.append(f"- **核对（联网）**：{c['web_check']}")
    return out


def human_check_items(c: dict) -> list[str]:
    """按新规矩必须转人工的联网条目（反证/无信号/无法验证）的摘要清单。"""
    items = []
    for e in (c.get("fact_check") or []):
        if e.get("verdict") in HC_VERDICTS:
            items.append(f"{e.get('claim', '')}（{e['verdict']}）"
                         + (f"：{e['conclusion']}" if e.get("conclusion") else ""))
    return items


def render_card(no: int, c: dict, w: dict) -> list[str]:
    ver_tag = f"（{w['ver']}）" if w.get("ver") else ""
    anchor = (f"{w['game']}{ver_tag} · {w['episode_title']} · "
              f"原文第 {w['line_start']}–{w['line_end']} 行")
    # 五维打分（规则14/19）：0~3 × 5，高=11~15 中=7~10 低=0~6
    dims = [("玩家帮助", int(c.get("help", 0))),
            ("具体程度", int(c.get("concrete", 0))),
            ("判断增量", int(c.get("delta", 0))),
            ("独特性", int(c.get("unique", 0))),
            ("成文能力", int(c.get("writing", 0)))]
    total = sum(s for _, s in dims)
    tier = "高" if total >= 11 else ("中" if total >= 7 else "低")
    mx = max(s for _, s in dims)
    parts = " ｜ ".join(
        f"{n} **{s}**" if s == mx else f"{n} {s}"
        for _, n, s in sorted(((i, n, s) for i, (n, s) in enumerate(dims)),
                              key=lambda t: (-t[2], t[0])))
    # 默认复选状态（规则17）：高=采用 低=删除 中=不勾
    if tier == "高":
        boxes = ["- [x] **采用**", "- [ ] 删除"]
    elif tier == "低":
        boxes = ["- [ ] 采用", "- [x] 删除"]
    else:
        boxes = ["- [ ] 采用", "- [ ] 删除"]
    out = [f"### 素材卡 {str(no).zfill(3)}｜{total}分", "",
           f"> 基础价值：{tier}（{total}/15）",
           f"> 分项：{parts}"]
    if c.get("use"):
        out.append(f"> 建议用途：{c['use']}")
    out.append("> 联网策略：" + (c.get("web_strategy") or "条件联网"))
    if c.get("judge_reason"):
        out.append(f"> 判断理由：{c['judge_reason']}")
    if c.get("tension_type") != "自我反转":
        for rel_no, rel_subject, rel_ver in c.get("_rel", []):
            out.append(f"> 相关联卡：素材卡 {str(rel_no).zfill(3)}"
                       f"《{rel_subject}》（{rel_ver}）")
    out.append("> 机会价值：待评估")
    out += ["", f"- **主题**：{c['subject']}",
            f"- **当时的细节**：{c['detail']}",
            f"- **我的感受与判断**：{c['feeling']}",
            f"- **可以说明什么**：{c['analysis']}"]
    if c.get("tension"):
        out.append(f"- **张力**：{c['tension']}")
        if c.get("tension_type"):
            out.append(f"- **张力类型**：{c['tension_type']}")
    if c.get("tension_type") == "自我反转":
        for rel_no, rel_subject, rel_ver in c.get("_rel", []):
            out.append(f"- 反转:参见素材卡 {str(rel_no).zfill(3)}"
                       f"（{rel_subject}，{rel_ver}）")
    out += ["", boxes[0], boxes[1], "",
            "<details>", "<summary><strong>证据与核对信息</strong></summary>",
            "",
            f"> **证据位置**：{anchor}",
            "> **"
            + ("玩家原话" if c.get("speaker", "玩家") == "玩家"
               and c.get("speaker_conf", "高") == "高"
               else f"{c.get('speaker', '待确认')}原话"
               f"（置信度{c.get('speaker_conf', '待确认')}）")
            + f"**：“{c['quote']}”", ""]
    out += render_web_block(c)
    hcitems = human_check_items(c)
    if hcitems:
        out.append("- **待人工（联网未闭环）**：" + "；".join(hcitems))
    if c.get("web_log"):
        out.append("- **核对记录**："
                   + re.sub(r"^待人工[:：]\s*", "", c["web_log"]))
    out += [f"- **说话人**：{c.get('speaker', '玩家')}",
            f"- **说话人置信度**：{c.get('speaker_conf', '高')}",
            "", "</details>", ""]
    return out


def find_context(todo: list, w: dict, quote: str) -> list[str]:
    """在原始窗口里定位原话所在句，返回该句±2句（带行号）作为人工判断上下文。"""
    src = None
    for cand in todo:
        if (cand.get("episode_title") == w.get("episode_title")
                and cand.get("line_start") == w.get("line_start")
                and cand.get("game") == w.get("game")
                and cand.get("ver") == w.get("ver")):
            src = cand
            break
    if src is None:
        return []
    sents = src["sentences"]
    target = norm(quote)
    joined = "".join(s["text"] for s in sents)
    pos = joined.find(target)
    if pos < 0:
        return [f"> {s['text']}" for s in sents[:3]]
    acc, idx = 0, 0
    for i, s in enumerate(sents):
        if acc <= pos < acc + len(s["text"]):
            idx = i
            break
        acc += len(s["text"])
    lo, hi = max(0, idx - 2), min(len(sents), idx + 3)
    return [f"> [{sents[i]['ordinal']}] {sents[i]['text']}"
            for i in range(lo, hi)]


def _bigrams(s: str) -> set[str]:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


TWIN_WINDOW_SIM = 0.60    # 孪生窗口阈值（跨版本句子几乎相同的窗口）
RARE_TERM_MAX_CARDS = 3   # 主题词出现卡数≤此值才算"稀有词"
RARE_TERM_MIN_SHARE = 1   # 跨版本卡共享稀有主题词≥此数即自动挂链
_CJK = re.compile(r"[\u4e00-\u9fff]{2}")


def _clean_bigrams(s: str) -> set[str]:
    """只保留纯汉字的二元组（剔除标点、英文、数字碎片）。"""
    return {t for t in _bigrams(s) if _CJK.fullmatch(t)}


def _window_text(todo: list, wkey: tuple) -> str:
    for w in todo:
        if (w.get("source_id"), w["episode_title"],
                w["line_start"]) == wkey:
            return "".join(s["text"] for s in w["sentences"])
    return ""


def auto_link_cross_version(cards_out: list, todo: list) -> list[tuple]:
    """跨版本自动匹配，两个可解释信号：
    ① 孪生窗口：两版本窗口原文几乎相同（同一段内容被重复转写/两份录像）；
    ② 稀有主题词：两卡的主题共享只在本批极少数卡出现的词（专有名词/机制名）。
    命中即双向挂"相关联卡"。返回自动配对清单供报表核对。"""
    wkeys = {(it["window"]["source_id"], it["window"]["episode_title"],
              it["window"]["line_start"]): it for it in cards_out}
    kb = {k: _bigrams(_window_text(todo, k)) for k in wkeys}
    # 稀有主题词表（subject 的纯汉字二元组，按出现卡数过滤）
    from collections import Counter
    subj_terms = [_clean_bigrams(it["card"]["subject"]) for it in cards_out]
    df = Counter(t for ts in subj_terms for t in ts)
    rare = [{t for t in ts if df[t] <= RARE_TERM_MAX_CARDS}
            for ts in subj_terms]
    pairs: list[tuple] = []
    linked: set[tuple] = set()

    def link(a, b, why: str):
        key = (min(a["no"], b["no"]), max(a["no"], b["no"]))
        if key in linked:
            return
        linked.add(key)
        pairs.append((a["no"], b["no"], why))
        ra = a["card"].setdefault("_rel", [])
        rb = b["card"].setdefault("_rel", [])
        if (b["no"], b["card"]["subject"], b["ver"]) not in ra:
            ra.append((b["no"], b["card"]["subject"], b["ver"]))
        if (a["no"], a["card"]["subject"], a["ver"]) not in rb:
            rb.append((a["no"], a["card"]["subject"], a["ver"]))

    for i, a in enumerate(cards_out):
        ka = (a["window"]["source_id"], a["window"]["episode_title"],
              a["window"]["line_start"])
        for j, b in enumerate(cards_out):
            if j <= i or a["window"]["game"] != b["window"]["game"] \
                    or a["ver"] == b["ver"]:
                continue
            kb2 = (b["window"]["source_id"], b["window"]["episode_title"],
                   b["window"]["line_start"])
            if ka in kb and kb2 in kb and _jaccard(kb[ka], kb[kb2]) \
                    >= TWIN_WINDOW_SIM:
                link(a, b, "孪生窗口")
                continue
            share = rare[i] & rare[j]
            if len(share) >= RARE_TERM_MIN_SHARE:
                link(a, b, "主题共词:" + "、".join(sorted(share)[:2]))
    return pairs


def run_from_json(path: str, todo: list, out_dir: Path, today: str,
                  cfg=None) -> None:
    """人工/AI 直接产卡模式：同一套逐字锁与渲染，只是卡由外部 JSON 提供。

    版式按规则16：文件头只有张数概览；完整卡片按 高/中/低 三个二级标题分组，
    组内按总分降序（同分按 玩家帮助→判断增量→独特性 降序）；
    卡号是稳定 ID：本批生成后固定，后续批次顺延，重排只动位置不改号。
    """
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    by_key = {(w.get("source_id"), w["episode_title"], w["line_start"]): w for w in todo}
    cards_out, human_check = [], []
    for item in items:
        w = by_key.get((item.get("source_id"), item.get("episode_title"),
                        item.get("window_line_start"))) or by_key.get(
            (None, item.get("episode_title"), item.get("window_line_start")))
        if not w:
            print(f"! 找不到窗口 {item.get('episode_title')} "
                  f"第{item.get('window_line_start')}行，跳过")
            continue
        seen = set()
        for c in item.get("cards", []):
            qn = norm(c.get("quote", ""))
            if not qn or qn in seen:
                continue
            seen.add(qn)
            if quote_ok(c.get("quote", ""), w):
                cards_out.append({"card": c, "window": {
                    k: w.get(k) for k in (
                        "game", "ver", "episode_id", "episode_title",
                        "source_id", "line_start", "line_end",
                        "density", "score")}})
            else:
                human_check.append({"card": c, "window": {
                    k: w.get(k) for k in ("game", "ver", "episode_title",
                                          "line_start", "line_end")}})

    # 稳定卡号：总分降序、同分按 玩家帮助→判断增量→独特性（规则16）
    def dims(c):
        return (int(c.get("help", 0)), int(c.get("delta", 0)),
                int(c.get("unique", 0)))

    def total(c):
        return sum(int(c.get(k, 0)) for k in
                   ("help", "concrete", "delta", "unique", "writing"))

    def tier(c):
        t = total(c)
        return "高" if t >= 11 else ("中" if t >= 7 else "低")

    cards_out.sort(key=lambda it: (-total(it["card"]),) +
                   tuple(-d for d in dims(it["card"]))[:1] +
                   tuple(-d for d in dims(it["card"]))[1:])
    for n, it in enumerate(cards_out, 1):
        it["no"] = n

    # 版本名+系列名（窗口→episodes→game_versions→games→series），按 游戏+版本 出一份文件
    from gws.db import connect
    conn = connect(cfg)
    try:
        ver_map = {r["episode_id"]: (r["series"], r["ver"])
                   for r in conn.execute(
            "SELECT e.id AS episode_id, v.name AS ver, "
            "COALESCE(se.name, '—') AS series FROM episodes e "
            "JOIN game_versions v ON v.id = e.version_id "
            "JOIN games g ON g.id = v.game_id "
            "LEFT JOIN series se ON se.id = g.series_id")}
    finally:
        conn.close()
    for it in cards_out:
        series, ver = ver_map.get(it["window"]["episode_id"], ("—", "default"))
        it["ver"] = ver
        it["series"] = series

    # 跨卡双向引用：卡的 related=[对方主题文本]，解析成卡号后两边都挂链接
    subj_map = {it["card"]["subject"]: (it["no"], it["ver"])
                for it in cards_out}
    for it in cards_out:
        for subj in it["card"].get("related", []):
            tgt = subj_map.get(subj)
            if not tgt or tgt[0] == it["no"]:
                continue
            rels = it["card"].setdefault("_rel", [])
            if (tgt[0], subj, tgt[1]) not in rels:
                rels.append((tgt[0], subj, tgt[1]))
            back = cards_out[tgt[0] - 1]["card"].setdefault("_rel", [])
            entry = (it["no"], it["card"]["subject"], it["ver"])
            if entry not in back:
                back.append(entry)

    # 跨版本自动匹配（算法兜底，不依赖写卡人手点）
    auto_pairs = auto_link_cross_version(cards_out, todo)
    if auto_pairs:
        print("自动跨版本配对：")
        for na, nb, why in auto_pairs:
            print(f"  卡{na:03d} ↔ 卡{nb:03d}（{why}）")

    sec_title = {"高": "◆ 高价值 ｜ 优先审核",
                 "中": "◇ 中价值 ｜ 按需保留",
                 "低": "· 低价值 ｜ 默认退出"}
    by_gv: dict[tuple, list] = {}
    for it in cards_out:
        by_gv.setdefault((it["window"]["game"], it["ver"]), []).append(it)

    written = []
    for (game, ver), group in sorted(by_gv.items()):
        group_series = next((it["series"] for it in group
                             if it.get("series")), "—")
        n_hi = sum(1 for it in group if tier(it["card"]) == "高")
        n_mid = sum(1 for it in group if tier(it["card"]) == "中")
        n_lo = len(group) - n_hi - n_mid
        md = [f"# 《{game}》素材卡草稿（{ver}）· {datetime.date.today()}"
              f"（待人工审核）", "",
              f"> 系列：{group_series} ｜ 游戏：{game} ｜ 版本：{ver}",
              f"> 来源：素材卡管线（screen_windows → coarse_gate → 精读）。",
              f"> 转录无时间戳，证据一律用「原文第X–Y行」行号锚点；"
              f"卡号=稳定ID，只移动展示位置不重编号。",
              f"> 每卡「AI辅助信息（联网）」块标明哪些信息来自外部核验、"
              f"哪些全部来自转录原文。", "",
              "## 先读我：什么是「张力」（10秒版）", "",
              "- 张力 = 这条体验里最反直觉、最想争辩、或与预期相反的那一下。"
              "没有张力的卡就是普通记录。",
              "- 张力类型：反预期 ｜ 价值观冲突 ｜ 与常识相反 ｜ 自我反转"
              "（标'反转:参见素材卡NN'）｜ 无张力。",
              "- 本文件里没有「张力/张力类型」两行的卡 = 无张力卡，禁止硬凑。", "",
              "## 现在只做这3件事", "",
              "- [ ] 1.【必填】逐卡确认复选框：高价值默认采用、中价值默认"
              "不勾、低价值默认删除（可覆盖；删除只退出成稿候选）",
              "- [ ] 2.【必填】核对各卡「核对记录」里标'待人工'的 ASR 变体"
              "与游戏内数值",
              "- [ ] 3.【必填】把文末'提交状态'改成'已填写'", "",
              f"## 价值概览", "",
              f"高价值 {n_hi} ｜ 中价值 {n_mid} ｜ 低价值 {n_lo}", ""]
        for sec in ("高", "中", "低"):
            grp = [it for it in group if tier(it["card"]) == sec]
            if not grp:
                continue
            md += [f"## {sec_title[sec]}", ""]
            for it in grp:
                md += render_card(it["no"], it["card"], it["window"])
        md += ["---", "", "提交状态：（待填写）", ""]
        fname = f"《{game}》素材卡草稿（{ver}）-{today}.md"
        (out_dir / fname).write_text("\n".join(md), encoding="utf-8")
        written.append(fname)
    # human_check（规则9/13）：逐字锁失败 + 各卡"待人工"核对项，每轮全量重写；
    # 按游戏+版本各一份，与卡片草稿文件一一对应
    hc_groups: dict[tuple, list] = {}
    for it in cards_out:
        c = it["card"]
        wl = re.sub(r"^待人工[:：]\s*", "", c.get("web_log", ""))
        hcitems = human_check_items(c)
        if not wl and not hcitems:
            continue
        # 新规矩：联网未闭环条目（存疑/无信号/无法验证）与旧"待人工"并列登记
        note = "；".join(x for x in ([wl] if wl else [])
                         + [f"联网未闭环：{h}" for h in hcitems])
        c = dict(c)
        c["web_log"] = note
        hc_groups.setdefault((it["window"]["game"], it["ver"]), []).append(
            ("待人工", c, it["window"], it["no"]))
    for item in human_check:
        w = item["window"]
        hc_groups.setdefault((w["game"], w.get("ver", "default")),
                             []).append(("锁失败", item["card"], w, None))
    for (game, ver), entries in sorted(hc_groups.items()):
        group_series = next((it["series"] for it in cards_out
                             if it["window"]["game"] == game
                             and it["ver"] == ver and it.get("series")), "—")
        hc = [f"# human_check（待人工填写）· {game}（{ver}）· "
              f"{datetime.date.today()}", "",
              f"> 系列：{group_series} ｜ 游戏：{game} ｜ 版本：{ver}",
              "> AI 已预填「AI辅助结论（联网）」，人只填「人工结论」；"
              "填完本文件，对应卡片草稿才改名归档。", ""]
        for n, (kind, c, w, no) in enumerate(entries, 1):
            ctx = find_context(todo, w, c.get("quote", ""))
            wl = re.sub(r"^待人工[:：]\s*", "", c.get("web_log", ""))
            if kind == "待人工":
                hc += [f"## 条目 {str(n).zfill(2)}",
                       f"- 窗口：{game} · {w['episode_title']}"
                       f"（素材卡 {str(no).zfill(3)}）",
                       f"- 主题线索：{c.get('subject', '')}",
                       f"- 卡内原话：「{c.get('quote', '')}」",
                       f"- 待人工核对：{wl}"]
                if ctx:
                    hc += [f"- 原文上下文（原话所在句前后各2句，"
                           f"[ ]内为原文行号）："] + ctx
                hc += render_web_block(c) or ["- AI辅助结论（联网）：无外部可核信息，以游戏画面/人工记忆为准"]
                hc += ["- 人工结论：（待填写）", ""]
            else:
                hc += [f"## 条目 {str(n).zfill(2)}",
                       f"- 窗口：{game} · {w['episode_title']}",
                       f"- 模型给的原话：「{c.get('quote', '')}」"
                       "（未逐字命中）",
                       f"- 主题线索：{c.get('subject', '')}"]
                if ctx:
                    hc += ["- 原文上下文（供回查比对）："] + ctx
                hc += render_web_block(c) or ["- AI辅助结论（联网）：无外部核验项（未通过逐字锁，优先回查原文）"]
                hc += ["- 人工结论：（待填写）", ""]
        n_total = len(entries)
        hc += ["---", "",
               f"提交状态：（待填写）", "",
               f"> 完成标准：{n_total} 条「人工结论」全部填上、"
               "本行改成「已填写」。"
               "验证方法：文件里搜「（待填写）」应为 0 处；"
               "AI 归档前会按此检查，不通过不改名归档。", ""]
        (out_dir / f"human_check-{game}-{ver}-{today}.md").write_text(
            "\n".join(hc), encoding="utf-8")
    if not hc_groups:
        (out_dir / f"human_check-{today}.md").write_text(
            f"# human_check · {datetime.date.today()}\n\n本轮无待人工条目。\n",
            encoding="utf-8")
    (out_dir / f"cards-state-{today}.json").write_text(
        json.dumps({"cards": cards_out, "human_check": human_check},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"=== 完成：合格卡 {len(cards_out)} 张，逐字锁拦下 "
          f"{len(human_check)} 条进 human_check")
    for f in written:
        print(f"产出：{out_dir / f}")


def main() -> None:
    limit = None
    from_json = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--from-json" in sys.argv:
        from_json = sys.argv[sys.argv.index("--from-json") + 1]
    cfg = load_config()
    screen_dir = cfg.exports_dir / "screening"
    files = sorted(screen_dir.glob("readlist-*.jsonl"))
    if not files:
        print("找不到 readlist-*.jsonl，先跑 coarse_gate.py")
        return
    src_file = files[-1]
    windows = [json.loads(l) for l in open(src_file, encoding="utf-8")]
    # 只处理 KEEP（MAYBE 排后备用）；小测试按名单顺序取
    keeps = [w for w in windows if w["gate"]["verdict"] == "KEEP"]
    maybes = [w for w in windows if w["gate"]["verdict"] == "MAYBE"]
    todo = (keeps + maybes)[:limit] if limit else (keeps + maybes)

    today = f"{datetime.date.today():%Y%m%d}"
    out_dir = cfg.exports_dir / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    if from_json:
        run_from_json(from_json, todo, out_dir, today, cfg)
        return

    cards_out = []      # 合格卡
    human_check = []    # 逐字锁不过的
    for i, w in enumerate(todo, 1):
        text = "\n".join(f"[{s['speaker']}] {s['text']}"
                         for s in w["sentences"])
        prompt = PROMPT.format(ls=w["line_start"], le=w["line_end"],
                               text=text)
        try:
            resp = ask_llm(prompt)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {w['episode_title']} 请求失败: {e}")
            continue
        valid, retry, seen = [], [], set()
        for c in resp.get("cards", []):
            qn = norm(c.get("quote", ""))
            if not qn or qn in seen:
                continue  # 空原话 / 同窗口重复卡
            seen.add(qn)
            (valid if quote_ok(c.get("quote", ""), w) else retry).append(c)
        if retry:  # 带错误重试一次
            fix_note = "\n".join(
                f"- 上次的quote不是原文：「{c.get('quote', '')[:50]}」"
                for c in retry)
            try:
                resp2 = ask_llm(prompt + f"\n\n注意！你上次这些quote不是逐字原文：\n{fix_note}\n请重新提取，quote必须逐字复制。")
                for c in resp2.get("cards", []):
                    if quote_ok(c.get("quote", ""), w):
                        valid.append(c)
                    elif c not in retry:
                        retry.append(c)
            except Exception:
                pass
        gate = w.get("gate", {})
        print(f"[{i}/{len(todo)}] {w['game']} {w['episode_title']}"
              f" 第{w['line_start']}行（{gate.get('verdict')}"
              f"/重{gate.get('importance')}）→ {len(valid)} 卡"
              f"，逐字锁拦下 {len(retry)}")
        for c in valid:
            cards_out.append({"card": c, "window": {
                k: w.get(k) for k in ("game", "episode_id", "episode_title",
                                      "source_id", "line_start", "line_end",
                                      "density", "score")}})
        for c in retry:
            human_check.append({"card": c, "window": {
                k: w[k] for k in ("game", "episode_title", "line_start",
                                  "line_end")}})

    # 写草稿（按窗口分组）
    md = [f"# 素材卡草稿 · {datetime.date.today()}（待人工审核）", "",
          f"> 模型：{LLM_MODEL}　窗口 {len(todo)}　合格卡 {len(cards_out)}"
          f"　逐字锁拦下 {len(human_check)}（见 human_check）",
          "> 卡号是临时展示号，人工审核后再定稳定编号。", ""]
    no = 0
    by_w = {}
    for item in cards_out:
        key = (item["window"]["game"], item["window"]["episode_title"],
               item["window"]["line_start"])
        by_w.setdefault(key, []).append(item["card"])
    for (game, ep, ls), cs in by_w.items():
        w = next(w for w in todo if w["game"] == game
                 and w["episode_title"] == ep and w["line_start"] == ls)
        md += [f"## {game} · {ep} · 第 {w['line_start']}–{w['line_end']} 行"
               f"（密度 {w.get('density')}）", ""]
        for c in cs:
            no += 1
            md += render_card(no, c, w)
    (out_dir / f"卡片草稿-{today}.md").write_text("\n".join(md),
                                                  encoding="utf-8")

    if human_check:
        hc = [f"# human_check（待人工填写）· {datetime.date.today()}", "",
              "> 以下条目的原话未通过逐字校验，需要人工回查原文；"
              "模型输出仅供线索。", ""]
        for n, item in enumerate(human_check, 1):
            c = item["card"]
            hc += [f"## 条目 {str(n).zfill(2)}",
                   f"- 窗口：{item['window']['game']} · "
                   f"{item['window']['episode_title']} · "
                   f"第 {item['window']['line_start']}–"
                   f"{item['window']['line_end']} 行",
                   f"- 模型给的原话：「{c.get('quote', '')}」（未逐字命中）",
                   f"- 主题线索：{c.get('subject', '')}", ""]
        (out_dir / f"human_check-{today}.md").write_text(
            "\n".join(hc), encoding="utf-8")

    (out_dir / f"cards-state-{today}.json").write_text(
        json.dumps({"cards": cards_out, "human_check": human_check},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== 完成：合格卡 {len(cards_out)} 张，逐字锁拦下 "
          f"{len(human_check)} 条进 human_check")
    print(f"草稿：{out_dir / f'卡片草稿-{today}.md'}")


if __name__ == "__main__":
    main()
