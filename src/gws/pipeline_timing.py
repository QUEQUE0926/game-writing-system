# -*- coding: utf-8 -*-
"""产线分阶段计时（2026-09-13 落地）。

记录"生成素材卡"链路上各阶段的真实耗时，存
`data/<env>/logs/timing-<游戏>-<日期>.jsonl`，每行一条：
    {"ts": "HH:MM:SS", "stage": "精读", "game": "命运之手",
     "event": "start"|"done", "seconds": 123.4, "note": "..."}

用法两路：
- 产线脚本内部：start 记 `t0 = time.monotonic()`，收尾调
  `stamp("粗判", game, seconds=time.monotonic()-t0, note=...)`；
- 手工阶段（精读/手写/联网核验）：`scripts/timing.py start/done <阶段>`。

done 不传 seconds 时自动找同游戏同阶段的最后一条 start 计算间隔；
跨午夜会算不准（按当天文件、只看时分秒）——会话内跑批足够。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from gws.config import load_config


def _path(game: str, cfg=None) -> Path:
    cfg = cfg or load_config()
    today = f"{datetime.now():%Y%m%d}"
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", game or "_global")
    return cfg.logs_dir / f"timing-{safe}-{today}.jsonl"


def _find_start_ts(p: Path, stage: str) -> str | None:
    if not p.exists():
        return None
    ts = None
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("stage") == stage and e.get("event") == "start":
                    ts = e.get("ts")
    except OSError:
        return None
    return ts


def stamp(stage: str, game: str = "_global", event: str = "done",
          seconds: float | None = None, note: str | None = None,
          cfg=None) -> dict:
    """记一条阶段时间；返回落盘的条目。event=done 且 seconds=None 时
    自动配对同游戏同阶段的最后一条 start 计算间隔（找不到记 None）。"""
    p = _path(game, cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    now = f"{datetime.now():%H:%M:%S}"
    if event == "done" and seconds is None:
        start_ts = _find_start_ts(p, stage)
        if start_ts:
            fmt = "%H:%M:%S"
            seconds = round(
                (datetime.strptime(now, fmt)
                 - datetime.strptime(start_ts, fmt)).total_seconds(), 1)
    entry = {"ts": now, "stage": stage, "game": game, "event": event,
             "seconds": seconds}
    if note:
        entry["note"] = note
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def summary(game: str, cfg=None) -> list[dict]:
    """当天该游戏的 done 条目列表（含 start 无配对、seconds=None 的），
    按落盘顺序。"""
    p = _path(game, cfg)
    out: list[dict] = []
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("event") == "done":
                out.append(e)
    return out
