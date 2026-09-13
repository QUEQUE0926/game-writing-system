# -*- coding: utf-8 -*-
"""素材卡写库：把 craft_cards 产出的 cards-state-<日期>.json 导入
material_cards + material_card_evidence（+ audit_log）。

前置：卡片草稿已通过人工审核、human_check 已回填归档（05 文档流程）。
本脚本只做机械写入与证据绑定，不做任何改写。

字段映射（卡片 JSON → material_cards 列，映射固定并记入 audit_log）：
  subject        → subject
  detail         → observation
  feeling        → experience
  analysis       → interpretation
  judge_reason   → judgement
  quote          → quote
  concrete       → evidence_strength（0~3，列宽 0~5）
  writing        → writing_value
  help           → author_interest（玩家帮助=作者可直接引用的亲历价值）
  unique         → reuse_value（独特性=跨文章复用潜力）
  可能的 cause   → possible_cause 暂空（卡源无此字段，不硬造）

证据绑定（material_card_evidence）：
  原话去空白后在窗口行号范围内的 segments 里逐字命中 → 绑定命中的 segment；
  命中 0 条 = 无原话锚点，拒绝入库（evidence_strength 高分必须有锚点）。
  命中多条全绑（同一句话被切成多个 segment 的情形）。

幂等：同 episode_id + 同 quote 去空白后已存在 → 跳过并报告，不重复入库。

用法（默认试跑不落库，--apply 才写）：
  python scripts/import_cards.py                        # 最新 cards-state
  python scripts/import_cards.py --file <path> --apply  # 指定文件落库
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.ids import new_id  # noqa: E402
from gws.migrations import migrate  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def find_state_file(cfg) -> Path:
    files = sorted((cfg.exports_dir / "cards").glob("cards-state-*.json"))
    if not files:
        raise SystemExit("找不到 cards-state-*.json，先跑 craft_cards.py")
    return files[-1]


def main() -> None:
    apply = "--apply" in sys.argv
    file_arg = None
    if "--file" in sys.argv:
        file_arg = sys.argv[sys.argv.index("--file") + 1]

    cfg = load_config()
    conn = connect(cfg)
    migrate(conn)
    try:
        path = Path(file_arg) if file_arg else find_state_file(cfg)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cards = data.get("cards", [])
        print(f"读入 {path}：合格卡 {len(cards)} 张"
              f"（human_check 条目不入库：{len(data.get('human_check', []))}）")

        existing = {(r["episode_id"], norm(r["quote"])) for r in conn.execute(
            "SELECT episode_id, quote FROM material_cards")}
        segs_by_ep: dict[str, list] = {}
        n_ok = n_skip = n_noanchor = 0
        for it in cards:
            c, w = it["card"], it["window"]
            ep = w.get("episode_id")
            if not ep:
                print(f"! 无 episode_id，跳过：{c.get('subject', '')}")
                n_noanchor += 1
                continue
            qn = norm(c.get("quote", ""))
            if (ep, qn) in existing:
                print(f"= 已存在，跳过：{c.get('subject', '')}")
                n_skip += 1
                continue
            if ep not in segs_by_ep:
                segs_by_ep[ep] = [s for s in conn.execute(
                    """SELECT s.id, s.line_start, s.line_end, s.text
                       FROM segments s
                       JOIN episode_segments es ON es.segment_id = s.id
                       WHERE es.episode_id = ?
                         AND s.line_end >= ? AND s.line_start <= ?
                       ORDER BY s.line_start""",
                    (ep, w["line_start"], w["line_end"]))]
            hits = [s["id"] for s in segs_by_ep[ep]
                    if qn and qn in norm(s["text"])]
            if not hits:
                print(f"! 原话未命中窗口 segment，拒绝入库："
                      f"{c.get('subject', '')}")
                n_noanchor += 1
                continue
            card_id = new_id()
            if apply:
                conn.execute(
                    """INSERT INTO material_cards
                       (id, episode_id, subject, observation, experience,
                        possible_cause, interpretation, judgement, quote,
                        evidence_strength, writing_value, author_interest,
                        reuse_value)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (card_id, ep, c["subject"],
                     c.get("detail", ""), c.get("feeling", ""), "",
                     c.get("analysis", ""), c.get("judge_reason", ""),
                     c.get("quote", ""),
                     int(c.get("concrete", 0)), int(c.get("writing", 0)),
                     int(c.get("help", 0)), int(c.get("unique", 0))))
                conn.executemany(
                    "INSERT INTO material_card_evidence VALUES (?,?)",
                    [(card_id, sid) for sid in hits])
                conn.execute(
                    """INSERT INTO audit_log
                       (id, event_name, entity_type, entity_id, detail)
                       VALUES (?, 'import_cards', 'material_card', ?, ?)""",
                    (new_id(), card_id,
                     json.dumps({"source_file": str(path),
                                 "window": [w["line_start"], w["line_end"]],
                                 "segments": hits,
                                 "mapping": "detail→observation, feeling→"
                                 "experience, analysis→interpretation, "
                                 "judge_reason→judgement, concrete→"
                                 "evidence_strength, writing→writing_value, "
                                 "help→author_interest, unique→reuse_value"},
                                ensure_ascii=False)))
            existing.add((ep, qn))
            n_ok += 1
        if apply:
            conn.commit()
        mode = "APPLY" if apply else "DRY-RUN"
        print(f"=== {mode}：入库 {n_ok}，已存在跳过 {n_skip}，"
              f"无锚点拒绝 {n_noanchor}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
