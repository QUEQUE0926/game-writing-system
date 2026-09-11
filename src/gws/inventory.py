# -*- coding: utf-8 -*-
"""档案清单：查询稳定 ID（CLI list）与导出只读 HTML 视图（export-html）。"""
from __future__ import annotations

import html
import sqlite3
from pathlib import Path

from .config import Config


def fetch_tree(conn: sqlite3.Connection) -> list[dict]:
    """返回 系列→游戏→版本 树（含 ID、状态、Source/Segment 计数）。"""
    rows = conn.execute(
        """
        SELECT s.id AS sid, s.name AS sname, s.status AS sstatus,
               g.id AS gid, g.name AS gname, g.status AS gstatus,
               v.id AS vid, v.name AS vname, v.status AS vstatus
        FROM series s
        LEFT JOIN games g ON g.series_id = s.id
        LEFT JOIN game_versions v ON v.game_id = g.id
        ORDER BY s.name, g.name, v.name
        """
    ).fetchall()
    tree: dict[tuple, dict] = {}
    for r in rows:
        sk = r["sid"]
        series = tree.setdefault(
            sk, {"id": r["sid"], "name": r["sname"], "status": r["sstatus"],
                 "games": {}})
        if r["gid"]:
            game = series["games"].setdefault(
                r["gid"], {"id": r["gid"], "name": r["gname"],
                           "status": r["gstatus"], "versions": {}})
            if r["vid"]:
                n_src = conn.execute(
                    "SELECT COUNT(*) c FROM sources WHERE version_id=?",
                    (r["vid"],)).fetchone()["c"]
                n_seg = conn.execute(
                    """SELECT COUNT(*) c FROM segments seg
                       JOIN sources src ON src.id = seg.source_id
                       WHERE src.version_id=?""", (r["vid"],)).fetchone()["c"]
                game["versions"][r["vid"]] = {
                    "id": r["vid"], "name": r["vname"],
                    "status": r["vstatus"], "sources": n_src,
                    "segments": n_seg}
    return list(tree.values())


def render_text(tree: list[dict]) -> str:
    lines = []
    for s in tree:
        lines.append(f"系列 {s['name']}  id={s['id']}  [{s['status']}]")
        for g in s["games"].values():
            lines.append(f"  游戏 {g['name']}  id={g['id']}  [{g['status']}]")
            for v in g["versions"].values():
                lines.append(
                    f"    版本 {v['name']}  id={v['id']}  [{v['status']}]"
                    f"  sources={v['sources']} segments={v['segments']}")
    return "\n".join(lines) if lines else "（库为空）"


def find_by_name(conn: sqlite3.Connection, query: str) -> dict[str, list[dict]]:
    """按名字模糊查三类档案，返回 {series, games, versions}。

    - series：主名或 id 前缀命中
    - games：主名、别名或 id 前缀命中（附系列门牌）
    - versions：版本名命中（附 游戏+系列 门牌）
    同名多命中全部并排返回，由调用方展示供人挑选（绝不擅自猜一个）。
    """
    like = f"%{query}%"

    def rowmap(r, kind):
        d = dict(r)
        d["kind"] = kind
        return d

    series = [rowmap(r, "series") for r in conn.execute(
        """SELECT id, name, status FROM series
           WHERE (name LIKE ? OR id LIKE ?) AND status!='trashed'
           ORDER BY name""", (like, like)).fetchall()]

    games = [rowmap(r, "game") for r in conn.execute(
        """SELECT g.id, g.name AS gname, g.status, s.name AS sname,
                  a.alias
           FROM games g
           JOIN series s ON s.id = g.series_id
           LEFT JOIN game_aliases a ON a.game_id = g.id
           WHERE (g.name LIKE ? OR a.alias LIKE ? OR g.id LIKE ?)
             AND g.status!='trashed'
           ORDER BY s.name, g.name""", (like, like, like)).fetchall()]
    # 主名与别名都命中的同一条游戏会出多行 → 去重（保留别名信息合并）
    merged: dict[str, dict] = {}
    for g in games:
        m = merged.setdefault(g["id"], {**g, "alias": g["alias"]})
        if g["alias"] and m["alias"] != g["alias"]:
            m["alias"] = f'{m["alias"]} / {g["alias"]}'
    games = list(merged.values())

    versions = [rowmap(r, "version") for r in conn.execute(
        """SELECT v.id, v.name AS vname, v.status,
                  g.name AS gname, g.id AS gid, s.name AS sname
           FROM game_versions v
           JOIN games g ON g.id = v.game_id
           JOIN series s ON s.id = g.series_id
           WHERE (v.name LIKE ? OR v.id LIKE ?) AND v.status!='trashed'
           ORDER BY s.name, g.name, v.name""", (like, like)).fetchall()]

    return {"series": series, "games": games, "versions": versions}


def render_find(hits: dict[str, list[dict]]) -> str:
    """把 find_by_name 的结果渲染成门牌清单文本。"""
    lines: list[str] = []
    for s in hits["series"]:
        lines.append(f"[系列] {s['name']}  id={s['id']}  [{s['status']}]")
    for g in hits["games"]:
        via = f"  (别名: {g['alias']})" if g["alias"] else ""
        lines.append(f"[游戏] {g['sname']} → {g['gname']}{via}"
                     f"  id={g['id']}  [{g['status']}]")
    for v in hits["versions"]:
        lines.append(f"[版本] {v['sname']} → {v['gname']} → {v['vname']}"
                     f"  id={v['id']}  [{v['status']}]")
    if not lines:
        return "（没有命中任何 系列/游戏/版本）"
    return "\n".join(lines)


def export_html(cfg: Config, conn: sqlite3.Connection) -> Path:
    """导出只读档案清单 HTML 到 exports/。返回文件路径。"""
    tree = fetch_tree(conn)
    e = html.escape

    parts = ["""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>游戏档案清单</title>
<style>
body{font-family:"Microsoft YaHei",sans-serif;margin:24px;background:#fafafa;color:#222}
h1{font-size:20px} .id{font-family:Consolas,monospace;font-size:12px;color:#666}
ul{list-style:none;padding-left:18px} li{margin:4px 0}
.badge{font-size:11px;padding:1px 6px;border-radius:8px;background:#ddd;margin-left:6px}
.badge.trashed{background:#f8c9c9}.badge.active{background:#cde8cd}
.cnt{color:#888;font-size:12px}
</style></head><body>
<h1>游戏档案清单（只读视图）</h1>"""]
    for s in tree:
        parts.append(f'<ul><li><b>系列 {e(s["name"])}</b> '
                     f'<span class="id">{e(s["id"])}</span>'
                     f'<span class="badge {e(s["status"])}">{e(s["status"])}</span>')
        for g in s["games"].values():
            parts.append(f'<ul><li><b>游戏 {e(g["name"])}</b> '
                         f'<span class="id">{e(g["id"])}</span>'
                         f'<span class="badge {e(g["status"])}">{e(g["status"])}</span>')
            if g["versions"]:
                parts.append("<ul>")
                for v in g["versions"].values():
                    parts.append(
                        f'<li>版本 {e(v["name"])} '
                        f'<span class="id">{e(v["id"])}</span>'
                        f'<span class="badge {e(v["status"])}">{e(v["status"])}</span> '
                        f'<span class="cnt">sources={v["sources"]}'
                        f' segments={v["segments"]}</span></li>')
                parts.append("</ul>")
            parts.append("</li></ul>")
        parts.append("</li></ul>")
    parts.append("</body></html>")

    cfg.ensure_dirs()
    out = cfg.exports_dir / "inventory.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
