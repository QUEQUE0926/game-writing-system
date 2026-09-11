# -*- coding: utf-8 -*-
"""第 4 步：Speaker 分类（规则轮）。

两种模式（按 Source 自动判定）：
- diarized：Source 内含 >=2 条 ^发言人N$ 标签段 → 标签后正文归映射说话人，
  标签段本身 content_type='noise'。映射默认 1→author, 2→teammate，
  其余 N → 保持 unknown 并在报表中列出。
- solo：无标签 → 全部 author，另用高置信模式把明显非人声挑出（ui）。

用法：
  python scripts/classify_speakers.py            # 报表（只读，不改库）
  python scripts/classify_speakers.py --apply    # 写库（含 audit_log）
环境：GWS_ENV / GWS_DATA_ROOT 照常生效（先在沙盒/试跑，确认后再进 dev）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402

MARKER_RE = re.compile(r"^发言人(\d+)$")
SPEAKER_MAP = {1: "author", 2: "teammate"}
# 按文件的标签映射修正（2026-09-12 侦察拍板，依据：teammate 抽样为游戏教程语音）：
# 星际争霸2 的"发言人2"实为游戏内语音/教程 NPC，不是真人队友。
SPEAKER_MAP_OVERRIDES = {"星际争霸2": {1: "author", 2: "game_audio"}}
HEADER_RE = re.compile(r"_原文$")  # 文件标题头行，如"镇邪Ⅱ 1-5_原文"
UI_PATTERNS = [
    re.compile(r"^【.+】$"),          # 【系统提示】样式
    re.compile(r"^警告"),             # 警告……（游戏内播报）
    re.compile(r"^检测到"),           # 检测到……（游戏内播报）
]

# 只分类 speaker 仍为 unknown 的段；不重跑已分类的（幂等 + 不覆盖人工修正）
def classify(conn, apply: bool, only_prefix: str | None = None) -> dict:
    header_ids = set()
    sources = conn.execute("""
        SELECT s.id, g.name AS game, v.name AS ver, s.filename
        FROM sources s
        JOIN game_versions v ON v.id = s.version_id
        JOIN games g ON g.id = v.game_id
        ORDER BY g.name, s.filename""").fetchall()
    for src in sources:
        first = conn.execute(
            "SELECT id FROM segments WHERE source_id=? ORDER BY ordinal LIMIT 1",
            (src["id"],)).fetchone()
        if first:
            header_ids.add(first["id"])

    report = []
    for src in sources:
        if only_prefix and not src["id"].startswith(only_prefix):
            continue
        segs = conn.execute("""
            SELECT id, text, speaker, content_type FROM segments
            WHERE source_id = ? ORDER BY ordinal""", (src["id"],)).fetchall()
        unknown = [s for s in segs if s["speaker"] == "unknown"]
        if not unknown:
            report.append({"game": src["game"], "ver": src["ver"],
                           "file": src["filename"], "mode": "skip(无unknown)",
                           "stats": {}, "samples": []})
            continue

        marker_count = sum(1 for s in unknown if MARKER_RE.match(s["text"]))
        diarized = marker_count >= 2
        updates = []  # (seg_id, speaker, content_type, note)

        if diarized:
            smap = dict(SPEAKER_MAP)
            smap.update(SPEAKER_MAP_OVERRIDES.get(src["game"], {}))
            current = None
            unmapped = set()
            for s in segs:
                if s["speaker"] != "unknown":
                    continue
                m = MARKER_RE.match(s["text"])
                if m:
                    n = int(m.group(1))
                    current = smap.get(n)
                    if current is None:
                        unmapped.add(f"发言人{n}")
                    # 标签段本身：不是台词 → noise（speaker 留 unknown）
                    updates.append((s["id"], "unknown", "noise", "marker"))
                elif s["id"] in header_ids:
                    updates.append((s["id"], "unknown", "noise", "header"))
                elif current:
                    updates.append((s["id"], current, s["content_type"], "diarized"))
            mode = f"diarized(map={smap},unmapped={sorted(unmapped) or '无'})"
        else:
            for s in unknown:
                if s["id"] in header_ids:
                    updates.append((s["id"], "unknown", "noise", "header"))
                elif any(p.match(s["text"]) for p in UI_PATTERNS):
                    updates.append((s["id"], "ui", "ui_text", "ui_pattern"))
                else:
                    updates.append((s["id"], "author", s["content_type"], "solo"))
            mode = "solo"

        stats: dict[str, int] = {}
        for _, spk, _, note in updates:
            key = f"{spk}/{note}"
            stats[key] = stats.get(key, 0) + 1

        samples = [s["text"][:40] for s in segs[:0]]  # 占位，见下
        # 抽样：每类前 3 条
        by_key: dict[str, list[str]] = {}
        text_by_id = {s["id"]: s["text"] for s in segs}
        for seg_id, spk, _, note in updates:
            by_key.setdefault(f"{spk}/{note}", [])
            if len(by_key[f"{spk}/{note}"]) < 3:
                by_key[f"{spk}/{note}"].append(text_by_id[seg_id][:40])

        if apply:
            for seg_id, spk, ctype, _note in updates:
                conn.execute(
                    "UPDATE segments SET speaker=?, content_type=? WHERE id=?",
                    (spk, ctype, seg_id))
            conn.execute(
                """INSERT INTO audit_log (id, event_name, entity_type, entity_id, detail)
                   VALUES (?, 'classify_speakers', 'source', ?, ?)""",
                (__import__("gws.ids", fromlist=["new_id"]).new_id(),
                 src["id"],
                 json.dumps({"mode": mode, "stats": stats}, ensure_ascii=False)))

        report.append({"game": src["game"], "ver": src["ver"],
                       "file": src["filename"], "mode": mode,
                       "stats": stats, "samples": by_key})

    if apply:
        conn.commit()
    return report


def main() -> None:
    apply = "--apply" in sys.argv
    only_prefix = None
    if "--source" in sys.argv:  # 可选：只处理 id 前缀匹配的源
        only_prefix = sys.argv[sys.argv.index("--source") + 1]
    cfg = load_config()
    conn = connect(cfg)
    try:
        report = classify(conn, apply, only_prefix=only_prefix)
        action = "已写入" if apply else "试跑（未改库）"
        print(f"=== Speaker 分类报表（{action}）env={cfg.env} root={cfg.data_root}")
        for r in report:
            print(f"\n--- {r['game']} / {r['ver']}  {r['file']}")
            print(f"    模式: {r['mode']}")
            if not r["stats"]:
                print("    (跳过)")
                continue
            for k, n in sorted(r["stats"].items()):
                print(f"    {k}: {n} 句")
            for k, texts in r["samples"].items():
                for t in texts:
                    print(f"      样例[{k}] {t}")
        total = {}
        for r in report:
            for k, n in r["stats"].items():
                spk = k.split("/")[0]
                total[spk] = total.get(spk, 0) + n
        print("\n=== 全库合计（本轮改动）:", json.dumps(total, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
