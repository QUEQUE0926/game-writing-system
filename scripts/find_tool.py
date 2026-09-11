# -*- coding: utf-8 -*-
"""查询档案小工具：双击 bat 运行，输入名字 → 显示门牌 + 本地文件路径。

用法：查询档案.bat（或 python find_tool.py [名字]）
环境：默认 dev，可用 GWS_ENV 切换。只读查询，不改任何数据。
"""
import os
import sys
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", os.environ.get("GWS_ENV", "dev"), "app.db")


def find(name: str) -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    like = f"%{name}%"

    hits = 0
    for table, label in (("series", "系列"), ("games", "游戏")):
        rows = con.execute(
            f"SELECT id, name, status FROM {table} WHERE name LIKE ? ORDER BY name", (like,)
        ).fetchall()
        for r in rows:
            hits += 1
            print(f"[{label}] {r['name']}  状态={r['status']}  id={r['id']}")

    # 按门牌联动：凡是名字命中的游戏/系列，把相关源文件都列出来
    game_ids = [
        r["id"]
        for r in con.execute(
            """
            SELECT g.id FROM games g WHERE g.name LIKE ?
            UNION
            SELECT g.id FROM games g JOIN series s ON g.series_id = s.id
            WHERE s.name LIKE ?
            """,
            (like, like),
        ).fetchall()
    ]
    for gid in game_ids:
        g = con.execute("SELECT name FROM games WHERE id=?", (gid,)).fetchone()
        versions = con.execute(
            "SELECT id, name FROM game_versions WHERE game_id=? ORDER BY created_at", (gid,)
        ).fetchall()
        for v in versions:
            sources = con.execute(
                "SELECT id, filename, relative_path, encoding FROM sources WHERE version_id=? ORDER BY imported_at",
                (v["id"],),
            ).fetchall()
            if not sources:
                continue
            print(f"\n■ {g['name']} · 版本[{v['name']}]（{len(sources)} 个源文件）")
            for s in sources:
                full = os.path.join(BASE, "data", os.environ.get("GWS_ENV", "dev"), s["relative_path"])
                segs = con.execute(
                    "SELECT COUNT(*) FROM segments WHERE source_id=?", (s["id"],)
                ).fetchone()[0]
                exists = "存在" if os.path.exists(full) else "丢失!"
                print(f"  {segs:>5} 句台词 | 原文{exists} | {full}")
                print(f"          归档名: {s['filename']} ({s['encoding']})")
    con.close()
    if hits == 0 and not game_ids:
        print(f"没查到名字带「{name}」的系列或游戏。试试换个关键词？")


def main() -> None:
    print(f"== 查询档案（环境: {os.environ.get('GWS_ENV', 'dev')}）==")
    print("输入名字的关键词（可直接回车退出）")
    while True:
        try:
            name = input("\n查什么> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not name:
            break
        print("-" * 60)
        try:
            find(name)
        except Exception as e:  # 只读查询，出错继续
            print(f"查询出错: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:  # 命令行直查模式
        find(" ".join(sys.argv[1:]))
    else:
        main()
    input("\n按回车关闭窗口...")
