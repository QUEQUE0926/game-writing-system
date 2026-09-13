# -*- coding: utf-8 -*-
"""分阶段计时命令行（安全支持 --help，无副作用参数检查）。

用法：
  python scripts/timing.py start <阶段> [--game 名] [--note 说明]
  python scripts/timing.py done  <阶段> [--game 名] [--seconds N] [--note 说明]
  python scripts/timing.py summary [--game 名]

供手工阶段（精读/手写/联网核验）打点；产线脚本（筛窗/粗判/渲染）
内部自记，不用本工具。记录存 data/<env>/logs/timing-<游戏>-<日期>.jsonl。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws import pipeline_timing  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(prog="timing.py",
                                 description="产线分阶段计时打点/汇总")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "done"):
        sp = sub.add_parser(name, help=f"记一条 {name}")
        sp.add_argument("stage", help="阶段名（如 精读 / 手写 / 联网核验）")
        sp.add_argument("--game", default="_global", help="游戏名（默认 _global）")
        sp.add_argument("--note", default=None, help="备注（如 28窗）")
        sp.add_argument("--seconds", type=float, default=None,
                        help="done 专用：显式耗时秒数；不传自动配对 start")
    sp = sub.add_parser("summary", help="汇总当天各阶段耗时")
    sp.add_argument("--game", default="_global", help="游戏名（默认 _global）")
    args = ap.parse_args()

    if args.cmd == "summary":
        entries = pipeline_timing.summary(args.game)
        if not entries:
            print(f"今天没有 {args.game} 的计时记录")
            return
        total = 0.0
        print(f"=== {args.game} 各阶段耗时 ===")
        for e in entries:
            s = e.get("seconds")
            mark = f"{s:>8.1f}s" if isinstance(s, (int, float)) else "   未配对"
            note = f" ｜ {e['note']}" if e.get("note") else ""
            print(f"{mark}  {e['stage']}{note}")
            if isinstance(s, (int, float)):
                total += s
        print(f"{'--------'}  合计 {total:.1f}s")
        return

    kwargs = {"game": args.game, "note": args.note}
    if args.cmd == "start":
        kwargs["event"] = "start"
    else:
        kwargs["seconds"] = args.seconds
    e = pipeline_timing.stamp(args.stage, **kwargs)
    tail = f" ({e['seconds']}s)" if e.get("seconds") is not None else ""
    print(f"计时[{e['event']}] {e['game']}/{e['stage']}{tail}"
          + (f" ｜ {e['note']}" if e.get("note") else ""))


if __name__ == "__main__":
    main()
