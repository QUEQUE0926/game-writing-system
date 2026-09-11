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
  python scripts/craft_cards.py --limit 3    # 小批量测试
  python scripts/craft_cards.py              # 全量精读名单
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


def render_card(no: int, c: dict, w: dict) -> list[str]:
    anchor = (f"{w['game']} · {w['episode_title']} · "
              f"原文第 {w['line_start']}–{w['line_end']} 行")
    out = [f"### 素材卡 {str(no).zfill(3)}｜待人工审核", ""]
    out += [f"- **主题**：{c['subject']}",
            f"- **当时的细节**：{c['detail']}",
            f"- **我的感受与判断**：{c['feeling']}",
            f"- **可以说明什么**：{c['analysis']}"]
    if c.get("tension"):
        out += [f"- **张力**：{c['tension']}"]
        if c.get("tension_type"):
            out += [f"- **张力类型**：{c['tension_type']}"]
    out += ["", f"> **证据位置**：{anchor}",
            f"> **玩家原话**：“{c['quote']}”",
            "", "- [ ] 采用", "- [ ] 删除", ""]
    return out


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
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
