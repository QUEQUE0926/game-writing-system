# -*- coding: utf-8 -*-
"""第 7 步升级：精读前粗判门控（本地双模型合议）。

岗位分工（2026-09-12 对考定案）：
- 主判官 qwen3:4b-instruct-2507：逐窗口 KEEP/MAYBE/DROP + 信号标签 + 重要度，
  JSON schema 强制格式（自由格式实测 11/20 解析失败，schema 20/20）；
- 复核员 deepseek-r1：只接"争议件"——规则密度排名本游戏前 30% 但 4B 没给 KEEP
  的窗口，r1 二审改 KEEP 则回精读名单；
- DROP 的窗口不删除，记录在案备查（宁多勿漏原则）。

输入：exports/screening/windows-<日期>.jsonl（screen_windows.py 产出，默认取最新）
输出：
- gate-state.json（累计判定状态，断点续跑依据）；
- 精读名单 readlist-<日期>.jsonl（KEEP+复议回岗窗口，按重要度×密度排序）；
- 每游戏粗判工作台 <游戏>-粗判-<日期>.md + 总索引。

用法：
  python scripts/coarse_gate.py                 # 处理最新 windows jsonl 全部
  python scripts/coarse_gate.py --limit 6       # 只判 6 个（小测试）
  python scripts/coarse_gate.py --game 灰烬之国  # 只判指定游戏
  python scripts/coarse_gate.py --force         # 忽略已有判定重跑
"""
from __future__ import annotations

import datetime
import json
import statistics
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402

OLLAMA_URL = "http://localhost:11434"
JUDGE_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
REVIEW_MODEL = "deepseek-r1:latest"
SEED = 42

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["KEEP", "MAYBE", "DROP"]},
        "signals": {"type": "array", "items": {"type": "string", "enum": [
            "explicit_opinion", "confusion", "learning", "failure_breakthrough",
            "opinion_change", "concrete_mechanic", "story_judgement",
            "comparison"]}},
        "importance": {"type": "integer", "minimum": 0, "maximum": 3},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "signals", "importance", "confidence", "reason"],
}
PROMPT = """你是游戏实况素材分拣员。给这段实况转录（含转写错别字）打标，输出 JSON。
- verdict：KEEP=明确有料 / MAYBE=可能有用 / DROP=纯闲聊叙述
- signals（最多3个）：explicit_opinion(明确好评差评) confusion(困惑) learning(学会机制)
  failure_breakthrough(失败或突破) opinion_change(观点前后变化) concrete_mechanic(具体机制数字)
  story_judgement(剧情评价) comparison(和其他游戏比)
- importance：0~3（0=无，3=核心素材）；confidence：low/medium/high
- reason：必须用中文，15 字以内
你只负责分拣，不判断"文章价值"。拿不准就 MAYBE，不许硬 DROP。

转录内容：
{text}"""

SIGNAL_CN = {
    "explicit_opinion": "明确观点", "confusion": "困惑", "learning": "学会",
    "failure_breakthrough": "失败突破", "opinion_change": "观点变化",
    "concrete_mechanic": "具体机制", "story_judgement": "剧情评价",
    "comparison": "对比",
}


def ask_ollama(model: str, window: dict, timeout: int = 600) -> dict:
    text = "\n".join(f"[{s['speaker']}] {s['text']}"
                     for s in window["sentences"])
    body = json.dumps({
        "model": model, "stream": False, "seed": SEED, "keep_alive": "15m",
        "format": SCHEMA, "prompt": PROMPT.format(text=text),
        "options": {"temperature": 0.6, "num_predict": 600},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", body,
                                 {"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(json.loads(r.read())["response"])


def gate_one(window: dict, state: dict, force: bool) -> dict:
    """判一个窗口（含断点跳过、争议复议）。返回判定 dict。"""
    key = f"{window['source_id']}:{window['ord_start']}-{window['ord_end']}"
    if not force and key in state:
        return state[key]
    j = None
    for attempt in (1, 2):  # 失败自动重试一次
        try:
            j = ask_ollama(JUDGE_MODEL, window)
            j["signals"] = j.get("signals", [])[:3]
            break
        except Exception as e:
            if attempt == 2:
                j = {"verdict": "ERROR", "signals": [], "importance": -1,
                     "confidence": "low", "reason": f"请求失败:{e}"[:80]}
    j["reviewed"] = False
    state[key] = j
    return j


def main() -> None:
    limit = None
    game_filter = None
    force = "--force" in sys.argv
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--game" in sys.argv:
        game_filter = sys.argv[sys.argv.index("--game") + 1]

    cfg = load_config()
    screen_dir = cfg.exports_dir / "screening"
    files = sorted(screen_dir.glob("windows-*.jsonl"))
    if not files:
        print("找不到 windows-*.jsonl，先跑 screen_windows.py")
        return
    src_file = files[-1]
    windows = [json.loads(l) for l in open(src_file, encoding="utf-8")]
    if game_filter:
        windows = [w for w in windows if w["game"].startswith(game_filter)]
    if limit:
        windows = windows[:limit]

    # 每游戏密度排名前 30% 的窗口集合（争议复议资格）
    by_game: dict[str, list] = {}
    for w in windows:
        by_game.setdefault(w["game"], []).append(w)
    top30: set[int] = set()
    for game, lst in by_game.items():
        lst.sort(key=lambda w: -w["score"])
        k = max(1, -(-len(lst) * 3 // 10))
        top30.update(id(w) for w in lst[:k])

    state_file = screen_dir / "gate-state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) \
        if state_file.exists() else {}

    print(f"=== 粗判门控（主判 {JUDGE_MODEL}，复议 {REVIEW_MODEL}）"
          f" 待判 {len(windows)} 窗，已存档 {len(state)} 条 ===")
    results = []
    n_new = 0
    for i, w in enumerate(windows, 1):
        j = gate_one(w, state, force)
        if j is not state.get(f"{w['source_id']}:{w['ord_start']}-{w['ord_end']}") \
                or force:
            n_new += 1
        # 争议复议：规则前 30% 但 4B 没给 KEEP
        if j["verdict"] in ("MAYBE", "DROP", "ERROR") and id(w) in top30:
            try:
                r = ask_ollama(REVIEW_MODEL, w)
                if r.get("verdict") == "KEEP":
                    j["verdict"] = "KEEP"
                    j["reviewed"] = True
                    j["reason"] = f"复议改KEEP:{r.get('reason', '')[:30]}"
            except Exception as e:
                print(f"  复议失败 {w['episode_title']}: {e}")
        results.append((w, j))
        state[f"{w['source_id']}:{w['ord_start']}-{w['ord_end']}"] = j
        if "--limit" not in sys.argv or n_new <= limit:
            print(f"[{i}/{len(windows)}] {w['game']} {w['episode_title']}"
                  f" 第{w['line_start']}行 → {j['verdict']}"
                  f"{'(复议)' if j.get('reviewed') else ''}"
                  f"|重{j['importance']} {j.get('reason', '')[:25]}")

    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    today = f"{datetime.date.today():%Y%m%d}"
    keep = [(w, j) for w, j in results if j["verdict"] == "KEEP"]
    maybe = [(w, j) for w, j in results if j["verdict"] == "MAYBE"]
    drop = [(w, j) for w, j in results if j["verdict"] in ("DROP", "ERROR")]
    keep.sort(key=lambda t: (-t[1]["importance"], -t[0]["score"]))

    readlist = out_dir = None
    if keep or maybe:
        readlist = screen_dir / f"readlist-{today}.jsonl"
        with open(readlist, "w", encoding="utf-8") as f:
            for w, j in keep + maybe:
                slim = {k: v for k, v in w.items() if not k.startswith("_")}
                slim["gate"] = {k: j[k] for k in
                                ("verdict", "signals", "importance",
                                 "confidence", "reason") if k in j}
                f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    # 每游戏工作台
    out_dir = screen_dir
    by_g: dict[str, list] = {}
    for w, j in results:
        by_g.setdefault(w["game"], []).append((w, j))
    index = ["# 粗判门控 · 总索引", "",
             f"> 生成时间：{datetime.date.today()}　窗口 {len(results)} 个："
             f"KEEP {len(keep)} / MAYBE {len(maybe)} / DROP或失败 {len(drop)}"
             f"（复议改判 {sum(1 for _, j in results if j.get('reviewed'))}）",
             f"> 精读名单：{readlist}", "",
             "| 游戏 | KEEP | MAYBE | DROP |", "|---|---|---|---|"]
    for game in sorted(by_g):
        lst = by_g[game]
        k = sum(1 for _, j in lst if j["verdict"] == "KEEP")
        m = sum(1 for _, j in lst if j["verdict"] == "MAYBE")
        d = len(lst) - k - m
        index.append(f"| [{game}]({game}-粗判-{today}.md) | {k} | {m} | {d} |")

        md = [f"# {game} · 粗判工作台", "",
              f"> KEEP（优先精读）/ MAYBE（次级批处理）/ DROP（备查）", "",
              "## ◆ KEEP ｜ 优先精读", ""]
        for w, j in lst:
            if j["verdict"] != "KEEP":
                continue
            sig = "、".join(SIGNAL_CN.get(s, s) for s in j["signals"])
            md += [f"### {w['episode_title']} 第{w['line_start']}行"
                   f"｜重{j['importance']}｜{sig}"
                   f"{'｜复议回岗' if j.get('reviewed') else ''}",
                   f"> {j['reason']}",
                   f"- 密度分 {w['score']}｜"
                   f"原文 {w['line_start']}–{w['line_end']} 行", ""]
        md += ["## ◇ MAYBE ｜ 次级批处理", ""]
        for w, j in lst:
            if j["verdict"] != "MAYBE":
                continue
            md.append(f"- {w['episode_title']} 第{w['line_start']}行"
                      f"｜重{j['importance']}｜{j['reason'][:40]}")
        md += ["", "## · DROP ｜ 备查，不精读", ""]
        for w, j in lst:
            if j["verdict"] not in ("DROP", "ERROR"):
                continue
            md.append(f"- {w['episode_title']} 第{w['line_start']}行"
                      f"｜{j['reason'][:40]}")
        (out_dir / f"{game}-粗判-{today}.md").write_text(
            "\n".join(md), encoding="utf-8")

    index_path = out_dir / f"粗判索引-{today}.md"
    index_path.write_text("\n".join(index), encoding="utf-8")
    ts = [0]
    print(f"\n=== 完成：KEEP {len(keep)} / MAYBE {len(maybe)} / "
          f"DROP或失败 {len(drop)}")
    print(f"精读名单：{readlist}")
    print(f"工作台：{index_path}")


if __name__ == "__main__":
    main()
