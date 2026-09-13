# -*- coding: utf-8 -*-
"""核验档案与自动挂载（2026-09-13 落地，见 05 文档「核验档案与自动挂载」节）。

每游戏一本档案 data/<env>/web_facts/<游戏名>.json：
- facts：事实核验条目（三件套齐全：结论含等级措辞+链接+来源页逐字片段），
  带 triggers 关键词；craft_cards --from-json 渲染前按关键词自动挂到卡上。
- community：社区佐证条目，供写卡人人工挑选挂载（程序不自动挂）。

红线（05「联网规矩」时效条）：volatile=true 的易变条目（价格/补丁/销量等）
verified_at 不是当日则拒绝自动挂载，由会话 AI 当日重核后更新日期再渲染；
不拿旧缓存当事实。
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from gws.config import load_config

ARCHIVE_DIR_NAME = "web_facts"

# 卡片正文参与触发匹配的字段
_HAYSTACK_FIELDS = ("subject", "detail", "feeling", "analysis", "quote")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def archive_path(game: str, cfg=None) -> Path:
    cfg = cfg or load_config()
    return cfg.data_root / ARCHIVE_DIR_NAME / f"{game}.json"


def load_archive(game: str, cfg=None) -> dict:
    """读档案；不存在时返回空档案（不报错，等同无条目可挂）。"""
    p = archive_path(game, cfg)
    if not p.exists():
        return {"game": game, "facts": [], "community": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_archive(game: str, data: dict, cfg=None) -> Path:
    p = archive_path(game, cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data, game=game)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def fact_entry(f: dict) -> dict:
    """档案条目 → 卡片 fact_check 条目（日期字段对齐渲染格式）。"""
    e = {"claim": f["claim"], "verdict": f["verdict"], "grade": f["grade"],
         "conclusion": f["conclusion"], "date": f["verified_at"]}
    if f.get("url"):
        e["url"] = f["url"]
    if f.get("snippet"):
        e["snippet"] = f["snippet"]
    return e


def community_entry(c: dict) -> dict:
    """档案条目 → 卡片 community_scan 条目（key 不落卡）。"""
    e = {k: c[k] for k in ("topic", "conclusion", "platform", "url",
                           "snippet", "date") if c.get(k)}
    return e


def auto_attach(cards: list, game: str, today: str | None = None,
                cfg=None) -> tuple[int, list[tuple[str, str]]]:
    """按 triggers 把档案 facts 自动挂到卡上（就地补 card['fact_check']）。

    - 命中任一触发词即挂；同 claim 已挂过则去重跳过；
    - volatile 且 verified_at != today：拒挂，记入 stale 清单返回。
    返回 (挂载条数, [(key, 上次核验日期), ...] 待当日重核清单)。
    """
    today = today or f"{date.today():%Y-%m-%d}"
    stale: list[tuple[str, str]] = []
    n = 0
    for f in load_archive(game, cfg).get("facts", []):
        if f.get("volatile") and f.get("verified_at") != today:
            stale.append((f.get("key", "?"), f.get("verified_at", "?")))
            continue
        triggers = [_norm(t) for t in (f.get("triggers") or [])]
        if not triggers:
            continue
        payload = fact_entry(f)
        for c in cards:
            hay = _norm("".join(str(c.get(k, "")) for k in _HAYSTACK_FIELDS))
            if not hay or not any(t in hay for t in triggers):
                continue
            existing = c.setdefault("fact_check", [])
            if any(e.get("claim") == payload["claim"] for e in existing):
                continue
            existing.append(dict(payload))
            n += 1
    return n, stale
