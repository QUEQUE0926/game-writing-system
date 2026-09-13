# -*- coding: utf-8 -*-
"""报告自动清理：同名模式的 dated 报告只留最新一份。

规矩（2026-09-13 用户拍板）：exports 下的报告只看最新，旧日期文件自动删。
只删调用方显式给出的命名模式，绝不碰 jsonl / gate-state.json 等机器中间件
（断点续跑和跨日流程还要靠它们）。
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

_DATE_TAIL = re.compile(r"-(\d{8})\.[^.]+$")


def prune_dated_reports(directory: Path, patterns: list[str],
                        keep_date: str) -> list[str]:
    """删除 directory 下匹配 patterns 且日期段不是 keep_date 的旧报告。

    patterns 为 fnmatch 文件名模式，"{date}" 占位 8 位日期段（如
    "*-筛选-{date}.md"）。返回被删除的文件名列表（升序）。
    """
    removed = []
    for f in sorted(Path(directory).iterdir()):
        if not f.is_file():
            continue
        for pat in patterns:
            if not fnmatch.fnmatch(f.name, pat.replace("{date}", "????????")):
                continue
            m = _DATE_TAIL.search(f.name)
            if m and m.group(1) != keep_date:
                f.unlink()
                removed.append(f.name)
            break  # 首个匹配的模式定生死：是今天就留，是旧日期就删
    return removed
