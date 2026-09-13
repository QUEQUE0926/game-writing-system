# -*- coding: utf-8 -*-
"""V2 P0：Event 精读提取（强模型替身版）。

职责边界（17_V2_REDIRECT §14 + 细化方案 §6，红线见文末）：
- 输入 readlist 窗口；程序从数据库取出窗口内 segments 的真实 id 做映射，
  模型只管用行号选证据（evidence=行号数组），原话/segment_id 一律程序侧带出；
- 本地 qwen3-4b-instruct-2507 当强模型替身跑通链路（理解质量上限受本地模型限制，
  供链路验证与人工评，不作为正式 Event 质量结论）；
- 输出 Event（Lite/Full）+ Question + 与已有 Event 的关系；
  Thread 聚合是 P1，不在本脚本；
- 不生成完整素材卡、不联网核验（只记 external_fact_needed）；
- confidence=LOW / 证据行号全部无效 / 档位与结构不一致 → 进复核队列，不混入正式件。

输出（exports/events/<游戏>-<版本>/）：
- events-full.jsonl / events-lite.jsonl / events-review.jsonl
- questions.jsonl / event-relations.jsonl
- <游戏>-<版本>-Event工作台-<日期>.md（人工评测用，含程序侧取出的原话证据）
- event-state-<游戏>-<版本>.json（EVT/Q 编号分配 + 缓存，重跑不换已分配的号）

用法：
  python scripts/extract_events.py --game 命运之手 --limit 10   # MVP 首轮：前 10 窗
  python scripts/extract_events.py --game 命运之手              # 该游戏全部 readlist
  python scripts/extract_events.py --force                      # 忽略缓存重跑（改 prompt 后）
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.report_prune import prune_dated_reports  # noqa: E402

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
PROMPT_VERSION = "v2"   # prompt 改了 bump 这个，缓存自动失效（17 文档 §30）
SEED = 42

EVENT_TYPE_ENUM = [
    "emotion_shift", "mechanism_learning", "opinion_change", "expectation_gap",
    "failure", "breakthrough", "strategy_change", "build_formation",
    "difficulty", "progression", "usability", "balance",
    "narrative_response", "performance_issue", "other",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "has_event": {"type": "boolean"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["lite", "full"]},
                    "title": {"type": "string"},
                    "event_type": {"type": "array",
                                   "items": {"type": "string",
                                             "enum": EVENT_TYPE_ENUM}},
                    "topics": {"type": "array",
                               "items": {"type": "string"}},
                    "state_before": {"type": "string"},
                    "trigger": {"type": "string"},
                    "state_after": {"type": "string"},
                    "change_before": {"type": "string"},
                    "change_after": {"type": "string"},
                    "experience_chain": {"type": "array",
                                         "items": {"type": "string"}},
                    "core_observation": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "boundary": {"type": "string"},
                    "tension": {"type": "string"},
                    "why_valuable": {"type": "string"},
                    "possible_question": {"type": "string"},
                    "external_fact_needed": {"type": "array",
                                             "items": {"type": "string"}},
                    "thread_signals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string",
                                         "enum": ["possible_setup",
                                                  "relation_hint",
                                                  "question_link"]},
                                "note": {"type": "string"},
                            },
                            "required": ["type", "note"],
                        },
                    },
                    "value_level": {"type": "string",
                                    "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "confidence": {"type": "string",
                                   "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "evidence": {"type": "array",
                                 "items": {"type": "integer"},
                                 "minItems": 1},
                },
                "required": ["level", "title", "event_type", "why_valuable",
                             "value_level", "confidence", "evidence"],
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "question_type": {"type": "string",
                                      "enum": ["design", "experience",
                                               "comparison", "mechanism",
                                               "cause", "evaluation"]},
                    "strength": {"type": "string",
                                 "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "related_event_indexes": {"type": "array",
                                              "items": {"type": "integer"}},
                },
                "required": ["question", "question_type", "strength"],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_index": {"type": "integer"},
                    "existing_event_ref": {"type": "string"},
                    "relation": {"type": "string",
                                 "enum": ["SAME", "DEVELOPS", "CONTRADICTS",
                                          "CAUSES", "SUPPORTS", "PARALLEL"]},
                    "confidence": {"type": "string",
                                   "enum": ["HIGH", "MEDIUM", "LOW"]},
                },
                "required": ["event_index", "existing_event_ref",
                             "relation", "confidence"],
            },
        },
    },
    "required": ["has_event", "events", "questions", "relations"],
}

# 代码侧兜底上限（schema 的 maxItems 不执行，坑26）
MAX_EVENTS = 4
MAX_QUESTIONS = 3
MAX_EVENT_TYPE = 3
MAX_TOPICS = 4
MAX_EVIDENCE = 12

SYSTEM_PROMPT = """你的任务不是总结实况，也不是生成文章素材卡。
你的任务是识别"体验事件"：玩家的情绪、认知、判断、策略、理解或行为发生了值得保存的变化。

只有满足以下至少一项才生成 Event：
A 玩家状态发生变化（期待→失望、困惑→理解、看不起→真香……）
B 玩家对机制形成新理解
C 玩家修改此前判断
D 出现具体体验问题
E 出现可支撑设计分析的现象
F 出现强烈但有明确对象的感受

以下默认不生成：普通操作播报、纯剧情复述、单独一句情绪词、无对象吐槽、
重复观点、没有新信息的二次抱怨、闲聊、读字幕、NPC 台词。

规则：
- 不要因为一句强烈情绪就生成事件，必须说明情绪针对什么、为什么值得保存；
- 不要把玩家的主观猜测写成游戏客观事实；
- 每个 full Event 必须写 boundary（这段证据不能证明什么）；
- 证据只能使用行号（每条发言行首 [L数字]），禁止改写、翻译或拼接原话；
- value_level=HIGH 用 full（写全 state_before/trigger/state_after/core_observation），
  MEDIUM/LOW 用 lite（写 change_before/change_after 即可）；
- tension 必须写成 "A vs B" 的矛盾格式，不要写主题名；
- topics 必须给 1~4 个话题词（如：成长系统 / 遭遇品质 / 装备构筑）；
- question 必须是开放式追问（为什么 / 如何 / 在什么条件下），
  禁止"是否 / 有没有 / 好不好"式的是非题；
- 如果当前内容只是重复此前的 Event，用 relations 指向它，不要重复生成；
- 证据不足就降低 confidence；confidence=LOW 也要输出（会进人工复核队列）。"""

USER_PROMPT = """【游戏背景】
游戏：{game}（版本：{ver}）
集：{episode}
进度：实况第 {line_start}–{line_end} 行的片段

【已有相关 Event（可能为空）】
{recent}

【本段实况（转写含错别字；行号即证据编号）】
{block}

按 JSON schema 输出。"""

EVENT_TYPE_CN = {
    "emotion_shift": "情绪转变", "mechanism_learning": "机制学习",
    "opinion_change": "观点反转", "expectation_gap": "预期落差",
    "failure": "失败", "breakthrough": "突破",
    "strategy_change": "策略调整", "build_formation": "构筑成型",
    "difficulty": "难度", "progression": "成长",
    "usability": "易用性", "balance": "平衡",
    "narrative_response": "剧情反应", "performance_issue": "性能问题",
    "other": "其他",
}
QUESTION_TYPE_CN = {
    "design": "设计", "experience": "体验", "comparison": "对比",
    "mechanism": "机制", "cause": "成因", "evaluation": "评价",
}


def block_key(w: dict) -> str:
    return f"{w['source_id']}:{w['ord_start']}-{w['ord_end']}"


def block_hash(w: dict) -> str:
    h = hashlib.sha1()
    h.update(PROMPT_VERSION.encode())
    h.update(MODEL.encode())
    h.update(json.dumps(w.get("sentences", []), ensure_ascii=False,
                        sort_keys=True).encode())
    return h.hexdigest()


def load_seg_map(conn, w: dict) -> dict[int, dict]:
    """窗口句子 ordinal → segment 真值（id/speaker/text），证据映射的唯一来源。"""
    ords = [s["ordinal"] for s in w.get("sentences", [])]
    if not ords:
        return {}
    marks = ",".join("?" * len(ords))
    rows = conn.execute(
        f"SELECT id, ordinal, speaker, text FROM segments "
        f"WHERE source_id=? AND ordinal IN ({marks})",
        (w["source_id"], *ords)).fetchall()
    return {r["ordinal"]: dict(r) for r in rows}


def render_block(w: dict) -> str:
    return "\n".join(f"[L{s['ordinal']}][{s['speaker']}] {s['text']}"
                     for s in w.get("sentences", []))


def ask_ollama(system: str, prompt: str, timeout: int = 600) -> dict:
    body = json.dumps({
        "model": MODEL, "stream": False, "seed": SEED, "keep_alive": "15m",
        "system": system, "format": SCHEMA, "prompt": prompt,
        "options": {"temperature": 0.3, "num_predict": 2600},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", body,
                                 {"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(json.loads(r.read())["response"])


def cap_event(e: dict) -> dict:
    e = dict(e)
    e["event_type"] = e.get("event_type", [])[:MAX_EVENT_TYPE]
    e["topics"] = e.get("topics", [])[:MAX_TOPICS]
    e["experience_chain"] = e.get("experience_chain", [])[:8]
    e["external_fact_needed"] = e.get("external_fact_needed", [])[:5]
    e["thread_signals"] = e.get("thread_signals", [])[:3]
    e["evidence"] = e.get("evidence", [])[:MAX_EVIDENCE]
    return e


def normalize_block(raw: dict, w: dict, seg_map: dict, known_evts: set[str],
                    next_evt: int, next_q: int) -> dict:
    """程序侧把关：证据行号校验映射、编号分配、复核分流。返回更新后的游标。"""
    elig = set(seg_map)
    evts, reviews, rels_out, qs_out = [], [], [], []
    assigned: dict[int, str] = {}   # 本块内 event 下标 → EVT 号
    retired = []
    for i, e in enumerate(raw.get("events", [])[:MAX_EVENTS]):
        e = cap_event(e)
        bad = [n for n in e["evidence"] if n not in elig]
        good = [n for n in e["evidence"] if n in elig]
        reasons = []
        if bad:
            reasons.append(f"证据行号无效:{bad[:5]}")
        if not good:
            e["block_key"] = block_key(w)
            reviews.append({"raw": e, "reason": "证据行号全部无效（未入库）"})
            continue
        e["evidence"] = good
        e["evidence_seg_ids"] = [seg_map[n]["id"] for n in good]
        e["block_key"] = block_key(w)
        lvl, val = e.get("level"), e.get("value_level")
        if val == "HIGH" and lvl != "full":
            reasons.append("档位结构不一致(HIGH应为full)")
        if val in ("MEDIUM", "LOW") and lvl == "full":
            reasons.append("档位结构不一致(MEDIUM/LOW应为lite)")
        if e.get("confidence") == "LOW":
            reasons.append("confidence=LOW")
        if reasons:
            e["review_reasons"] = reasons
            reviews.append(e)
        else:
            evts.append(e)
        assigned[i] = f"EVT-{next_evt:04d}"
        e["evt_id"] = assigned[i]
        next_evt += 1
    for r in raw.get("relations", []):
        ref = r.get("existing_event_ref", "")
        if ref in known_evts or ref in assigned.values():
            rels_out.append({**r, "from_evt": assigned.get(
                r.get("event_index"), "")})
        else:
            retired.append(f"relation目标未知:{ref}")
    for q in raw.get("questions", [])[:MAX_QUESTIONS]:
        qs_out.append({**q, "q_id": f"Q-{next_q:03d}",
                       "block": block_key(w)})
        next_q += 1
    rec = {
        "window": {k: w[k] for k in ("game", "ver", "episode_title",
                                     "source_id", "ord_start", "ord_end",
                                     "line_start", "line_end") if k in w},
        "events": evts, "reviews": reviews,
        "questions": qs_out, "relations": rels_out,
        "notes": retired,
    }
    return rec, next_evt, next_q


def recent_events_text(state: dict, cur_key: str, limit: int = 5) -> str:
    out = []
    for k, rec in state["blocks"].items():
        if k == cur_key:
            break
        for e in rec.get("events", []):
            out.append(f"{e['evt_id']} {e.get('title', '')}"
                       f"（之后：{e.get('state_after') or e.get('change_after', '')[:40]}）")
    return "\n".join(out[-limit:]) or "（无）"


def quote_lines(e: dict, seg_map: dict) -> list[str]:
    lines = []
    for n in e.get("evidence", [])[:6]:
        s = seg_map.get(n)
        if s:
            lines.append(f"[L{n}][{s['speaker']}] {s['text']}")
    return lines


def write_outputs(gdir: Path, state: dict, today: str, model: str) -> Path:
    full, lite, review, qs, rels = [], [], [], [], []
    for rec in state["blocks"].values():
        full += [e for e in rec["events"] if e.get("level") == "full"]
        lite += [e for e in rec["events"] if e.get("level") == "lite"]
        review += rec.get("reviews", [])
        qs += rec.get("questions", [])
        rels += rec.get("relations", [])
    smaps_file = gdir / "event-seg-maps.json"
    raw_maps = json.loads(smaps_file.read_text(encoding="utf-8")) \
        if smaps_file.exists() else {}
    seg_maps = {k: {int(n): s for n, s in v.items()}
                for k, v in raw_maps.items()}

    def dump(name: str, rows: list) -> None:
        with open(gdir / name, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump("events-full.jsonl", full)
    dump("events-lite.jsonl", lite)
    dump("events-review.jsonl", review)
    dump("questions.jsonl", qs)
    dump("event-relations.jsonl", rels)

    # 工作台：人工评测用，证据原话由程序侧从 seg_map/库中还原（渲染时取）
    game, ver = state["game"], state["ver"]
    md = [f"# 《{game}》（{ver}）· Event 精读工作台", "",
          f"> 生成时间：{today}　替身模型 {model}（prompt {PROMPT_VERSION}）"
          f"——理解质量上限受本地模型限制，本报告供链路验证与人工评测，"
          f"非正式 Event 质量结论。",
          f"> Event {len(full) + len(lite)}（full {len(full)} / lite {len(lite)}）"
          f"｜复核 {len(review)}｜Question {len(qs)}｜关系 {len(rels)}", ""]
    for title, rows, tag in (("◆ HIGH/full", full, "full"),
                             ("◇ MEDIUM·LOW/lite", lite, "lite")):
        if not rows:
            continue
        md += [f"## {title}", ""]
        for e in rows:
            types = "、".join(EVENT_TYPE_CN.get(t, t)
                             for t in e.get("event_type", []))
            md.append(f"### {e['evt_id']} ｜ {e.get('value_level')}"
                      f"｜{e.get('confidence')}｜ {e.get('title', '')}")
            md.append(f"- 类型：{types}｜话题：{'、'.join(e.get('topics', []))}")
            if tag == "full":
                md += [f"- 之前：{e.get('state_before', '')}",
                       f"- 触发：{e.get('trigger', '')}",
                       f"- 之后：{e.get('state_after', '')}"]
                if e.get("experience_chain"):
                    md.append("- 体验链：" + " → ".join(e["experience_chain"]))
                if e.get("core_observation"):
                    md.append(f"- 核心观察：{e['core_observation']}")
                if e.get("interpretation"):
                    md.append(f"- 解读：{e['interpretation']}")
                if e.get("boundary"):
                    md.append(f"- 边界：{e['boundary']}")
            else:
                md.append(f"- 变化：{e.get('change_before', '')} → "
                          f"{e.get('change_after', '')}")
            if e.get("tension"):
                md.append(f"- 张力：{e['tension']}")
            md.append(f"- 价值：{e.get('why_valuable', '')}")
            if e.get("possible_question"):
                md.append(f"- 追问：{e['possible_question']}")
            for line in quote_lines(e, seg_maps.get(e.get("block_key", ""), {})):
                md.append(f"> {line}")
            md.append("")
    if review:
        md += ["## ⚠ 复核队列（人工定去留）", ""]
        for e in review:
            if "raw" in e:
                md.append(f"- ✗ 丢弃：{e['raw'].get('title', '?')}"
                          f"——{e['reason']}")
                continue
            md.append(f"### {e.get('evt_id', '?')} ｜ {e.get('value_level')}"
                      f"｜ {e.get('title', '')}")
            md.append(f"- 原因：{'；'.join(e.get('review_reasons', []))}")
            md.append(f"- 价值：{e.get('why_valuable', '')}")
            md.append("")
    if qs:
        md += ["## ？Question", ""]
        for q in qs:
            qt = QUESTION_TYPE_CN.get(q.get("question_type"),
                                      q.get("question_type", ""))
            md.append(f"- {q['q_id']}（{qt}/{q.get('strength')}）"
                      f"{q.get('question', '')}")
        md.append("")
    if rels:
        md += ["## ↔ 与已有 Event 的关系", ""]
        for r in rels:
            md.append(f"- {r.get('from_evt', '?')} → {r['existing_event_ref']}"
                      f"：{r['relation']}（{r.get('confidence')}）")
        md.append("")
    path = gdir / f"{game}-{ver}-Event工作台-{today}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def main() -> None:
    t0 = time.monotonic()
    limit = None
    game_filter = None
    force = "--force" in sys.argv
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--game" in sys.argv:
        game_filter = sys.argv[sys.argv.index("--game") + 1]

    cfg = load_config()
    screen_dir = cfg.exports_dir / "screening"
    files = sorted(screen_dir.glob("readlist-*.jsonl"))
    if not files:
        print("找不到 readlist-*.jsonl，先跑 coarse_gate.py")
        return
    windows = [json.loads(l) for l in open(files[-1], encoding="utf-8")]
    if game_filter:
        windows = [w for w in windows if w["game"].startswith(game_filter)]
    if limit:
        windows = windows[:limit]
    if not windows:
        print("没有匹配的窗口")
        return

    by_gv: dict[tuple, list] = {}
    for w in windows:
        by_gv.setdefault((w["game"], w.get("ver", "default")), []).append(w)

    conn = connect(cfg)
    today = f"{datetime.date.today():%Y%m%d}"
    try:
        for (game, ver), ws in sorted(by_gv.items()):
            gdir = cfg.exports_dir / "events" / f"{game}-{ver}"
            gdir.mkdir(parents=True, exist_ok=True)
            state_file = gdir / f"event-state-{game}-{ver}.json"
            state = json.loads(state_file.read_text(encoding="utf-8")) \
                if state_file.exists() else {}
            state.setdefault("blocks", {})
            state.setdefault("next_evt", 1)
            state.setdefault("next_q", 1)
            state["game"], state["ver"] = game, ver
            seg_maps: dict[str, dict] = {}
            known_evts = {e["evt_id"] for r in state["blocks"].values()
                          for e in r.get("events", [])}

            print(f"=== Event 提取：《{game}》（{ver}）窗口 {len(ws)} 个"
                  f"（缓存 {sum(1 for w in ws if block_key(w) in state['blocks'] and not force)} 条）===")
            for i, w in enumerate(ws, 1):
                key = block_key(w)
                h = block_hash(w)
                seg_map = load_seg_map(conn, w)
                seg_maps[key] = {str(n): {"id": s["id"], "speaker": s["speaker"],
                                          "text": s["text"]}
                                 for n, s in seg_map.items()}
                rec = state["blocks"].get(key)
                if not force and rec and rec.get("hash") == h:
                    print(f"[{i}/{len(ws)}] {w['episode_title']}"
                          f"（缓存命中，Event "
                          f"{len(rec.get('events', []))}）")
                    continue
                prompt = USER_PROMPT.format(
                    game=game, ver=ver, episode=w["episode_title"],
                    line_start=w["line_start"], line_end=w["line_end"],
                    recent=recent_events_text(state, key),
                    block=render_block(w))
                try:
                    raw = ask_ollama(SYSTEM_PROMPT, prompt)
                except Exception as e:
                    print(f"[{i}/{len(ws)}] {w['episode_title']} 请求失败：{e}")
                    continue
                rec, state["next_evt"], state["next_q"] = normalize_block(
                    raw, w, seg_map, known_evts,
                    state["next_evt"], state["next_q"])
                rec["hash"] = h
                for e in rec["events"]:
                    known_evts.add(e["evt_id"])
                state["blocks"][key] = rec
                print(f"[{i}/{len(ws)}] {w['episode_title']} → Event "
                      f"{len(rec['events'])}（复核 {len(rec['reviews'])}）"
                      f"｜问 {len(rec['questions'])}｜关系 {len(rec['relations'])}")
                state_file.write_text(json.dumps(state, ensure_ascii=False),
                                      encoding="utf-8")

            state_file.write_text(json.dumps(state, ensure_ascii=False),
                                  encoding="utf-8")
            (gdir / "event-seg-maps.json").write_text(
                json.dumps(seg_maps, ensure_ascii=False), encoding="utf-8")
            md = write_outputs(gdir, state, today, MODEL)
            pruned = prune_dated_reports(gdir, [f"*-Event工作台-{{date}}.md"],
                                         today)
            n_ev = sum(len(r.get("events", []))
                       for r in state["blocks"].values())
            n_rev = sum(len(r.get("reviews", []))
                        for r in state["blocks"].values())
            print(f"完成：《{game}》（{ver}）Event {n_ev}｜复核 {n_rev}")
            print(f"工作台：{md}")
            if pruned:
                print(f"清理旧报告 {len(pruned)} 份")
    finally:
        conn.close()

    from gws import pipeline_timing
    e = pipeline_timing.stamp(
        "Event提取", game_filter or "_global",
        seconds=round(time.monotonic() - t0, 1),
        note=f"窗口{len(windows)}", cfg=cfg)
    print(f"⏱ 计时：Event提取 {e['seconds']}s 已记 "
          f"{pipeline_timing._path(game_filter or '_global', cfg).name}")


if __name__ == "__main__":
    main()
