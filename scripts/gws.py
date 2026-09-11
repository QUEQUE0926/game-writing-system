# -*- coding: utf-8 -*-
"""gws CLI：环境初始化、建档、导入。

用法：
    python scripts/gws.py init --env dev
    python scripts/gws.py info --env test
    python scripts/gws.py create-series --env dev --name "系列名"
    python scripts/gws.py create-game   --env dev --name "游戏名" [--series <id>]
    python scripts/gws.py create-version --env dev --game <id> --name "1.0"
    python scripts/gws.py import-txt    --env dev --version <id> --file merged.txt
    python scripts/gws.py auto-import   --env dev [--dry-run]
        # 把 txt 丢进 data/<env>/inbox/auto/，文件名「游戏名 - 版本.txt」自动建档导入
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.import_service import import_source  # noqa: E402
from gws.migrations import current_version, migrate  # noqa: E402
from gws.repositories import (GameRepository, SeriesRepository,  # noqa: E402
                              VersionRepository)
from gws.validation import ValidationError  # noqa: E402


def _open(env: str):
    cfg = load_config(env)
    conn = connect(cfg)
    migrate(conn)
    return cfg, conn


def cmd_init(env: str) -> int:
    cfg, conn = _open(env)
    try:
        print(f"[init] env={cfg.env} db={cfg.db_path}")
        print(f"[init] 当前 schema version: {current_version(conn)}")
        return 0
    finally:
        conn.close()


def cmd_info(env: str) -> int:
    cfg = load_config(env)
    exists = cfg.db_path.exists()
    print(f"env={cfg.env}")
    print(f"db={cfg.db_path} exists={exists}")
    if exists:
        conn = connect(cfg)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            print(f"tables({len(tables)})={tables}")
            print(f"schema_version={current_version(conn)}")
        finally:
            conn.close()
    return 0


def cmd_create_series(env: str, name: str) -> int:
    _, conn = _open(env)
    try:
        sid = SeriesRepository(conn, load_config(env)).create(name)
        print(f"series_id={sid}")
        return 0
    finally:
        conn.close()


def cmd_create_game(env: str, name: str, series_id: str | None) -> int:
    _, conn = _open(env)
    try:
        gid = GameRepository(conn, load_config(env)).create(name, series_id)
        print(f"game_id={gid}")
        return 0
    finally:
        conn.close()


def cmd_create_version(env: str, game_id: str, name: str) -> int:
    _, conn = _open(env)
    try:
        vid = VersionRepository(conn, load_config(env)).create(game_id, name)
        print(f"version_id={vid}")
        return 0
    finally:
        conn.close()


def cmd_import_txt(env: str, version_id: str, file: str) -> int:
    cfg, conn = _open(env)
    try:
        result = import_source(cfg, version_id, Path(file))
        label = "去重跳过（同文件已导入）" if result["dedup"] \
            else f"新增 {result['segments']} 个 Segment"
        print(f"source_id={result['source_id']}  {label}")
        return 0
    finally:
        conn.close()


def cmd_auto_import(env: str, dry_run: bool) -> int:
    cfg, conn = _open(env)
    try:
        from gws.auto_import import auto_import
        result = auto_import(cfg, conn, dry_run=dry_run)
        if result["dry_run"]:
            print("[预览] 将执行以下导入（不会真正建库）：")
            for p in result["plan"]:
                series = f"系列[{p['series']}] " if p["series"] else ""
                print(f"  {p['file']}  →  {series}游戏[{p['game']}] 版本[{p['version']}]")
            if not result["plan"]:
                print("  （inbox/auto/ 下没有 txt）")
            return 0
        if not result["results"]:
            print("inbox/auto/ 下没有 txt，把文件命名为「游戏名 - 版本.txt」后重试")
            return 0
        for r in result["results"]:
            series = f"系列[{r['series']}] " if r["series"] else ""
            tag = "去重跳过" if r["dedup"] else f"{r['segments']} 个 Segment"
            print(f"  {r['file']}  →  {series}游戏[{r['game']}] "
                  f"版本[{r['version']}] source={r['source_id']}  {tag}")
        return 0
    finally:
        conn.close()


def cmd_rename(env: str, kind: str, object_id: str, name: str) -> int:
    _, conn = _open(env)
    try:
        repos = {"series": SeriesRepository, "game": GameRepository,
                 "version": VersionRepository}
        repo = repos[kind](conn, load_config(env))
        repo.rename(object_id, name)
        print(f"已改名 {kind} {object_id} → {name}（引用与数据不受影响）")
        return 0
    finally:
        conn.close()


def cmd_add_alias(env: str, game_id: str, alias: str) -> int:
    _, conn = _open(env)
    try:
        GameRepository(conn, load_config(env)).add_alias(game_id, alias)
        print(f"已为游戏 {game_id} 添加别名: {alias}")
        return 0
    finally:
        conn.close()


def cmd_prepare(env: str, game: str, version: str | None,
                series: str | None, open_folder: bool) -> int:
    """快速建档：按命名规则创建 inbox/auto/[系列/]游戏 - 版本/ 文件夹。"""
    import re
    import subprocess
    cfg = load_config(env)
    cfg.ensure_dirs()
    if version:
        folder_name = f"{game} - {version}"
    else:
        folder_name = game
        version = "(导入时默认 default)"
    # 建档文件夹放在 auto/ 下（是否带系列子层由 --series 决定）
    base = cfg.inbox_dir / "auto"
    if series:
        base = base / series
    target = base / folder_name
    target.mkdir(parents=True, exist_ok=True)
    print(f"文件夹已就绪: {target}")
    print(f"  → 将导入为 系列[{series or '无'}] 游戏[{game}] 版本[{version}]")
    print(f"  把该版本的 txt 直接放进这个文件夹，然后运行:")
    print(f"  python scripts/gws.py auto-import --env {env}")
    if open_folder:
        subprocess.Popen(["explorer", str(target)])
    return 0


def cmd_import_files(env: str, series: str | None, files: list[str]) -> int:
    """拖放入口：直接按路径导入 txt，文件名规则同 auto-import。"""
    cfg, conn = _open(env)
    try:
        from gws.auto_import import import_files
        result = import_files(cfg, conn, files, series=series)
        for r in result["results"]:
            if "error" in r:
                print(f"  [跳过] {r['file']} — {r['error']}")
                continue
            series_txt = f"系列[{r['series']}] " if r["series"] else ""
            tag = "去重跳过" if r["dedup"] else f"{r['segments']} 个 Segment"
            print(f"  {r['file']}  →  {series_txt}游戏[{r['game']}] "
                  f"版本[{r['version']}] source={r['source_id']}  {tag}")
        return 0
    finally:
        conn.close()


def cmd_list(env: str) -> int:
    cfg, conn = _open(env)
    try:
        from gws.inventory import fetch_tree, render_text
        print(render_text(fetch_tree(conn)))
        return 0
    finally:
        conn.close()


def cmd_find(env: str, query: str) -> int:
    cfg, conn = _open(env)
    try:
        from gws.inventory import find_by_name, render_find
        print(render_find(find_by_name(conn, query)))
        return 0
    finally:
        conn.close()


def cmd_export_html(env: str, open_browser: bool) -> int:
    import webbrowser
    cfg, conn = _open(env)
    try:
        from gws.inventory import export_html
        out = export_html(cfg, conn)
        print(f"已导出: {out}")
        if open_browser:
            webbrowser.open(f"file:///{out}")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="gws")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--env", default=os.environ.get("GWS_ENV", "dev"),
         choices=["dev", "test", "prod"])
        return p

    add("init")
    add("info")
    add("list")
    p = add("find"); p.add_argument("query", help="按名字模糊查 系列/游戏/版本")
    p = add("export-html"); p.add_argument("--open", action="store_true")
    p = add("create-series"); p.add_argument("--name", required=True)
    p = add("create-game"); p.add_argument("--name", required=True)
    p.add_argument("--series", default=None)
    p = add("create-version"); p.add_argument("--game", required=True)
    p.add_argument("--name", required=True)
    p = add("import-txt"); p.add_argument("--version", required=True)
    p.add_argument("--file", required=True)
    p = add("auto-import"); p.add_argument("--dry-run", action="store_true")
    for kind in ("series", "game", "version"):
        p = add(f"rename-{kind}")
        p.add_argument("--id", required=True)
        p.add_argument("--name", required=True)
    p = add("add-alias"); p.add_argument("--game", required=True)
    p.add_argument("--alias", required=True)
    p = add("prepare")
    p.add_argument("--game", required=True)
    p.add_argument("--version", default=None)
    p.add_argument("--series", default=None)
    p.add_argument("--open", action="store_true")
    p = sub.add_parser("import-files")
    p.add_argument("--env", default=os.environ.get("GWS_ENV", "dev"),
         choices=["dev", "test", "prod"])
    p.add_argument("--series", default=None)
    p.add_argument("files", nargs="+")

    args = parser.parse_args()
    try:
        if args.command == "init":
            return cmd_init(args.env)
        if args.command == "info":
            return cmd_info(args.env)
        if args.command == "list":
            return cmd_list(args.env)
        if args.command == "find":
            return cmd_find(args.env, args.query)
        if args.command == "export-html":
            return cmd_export_html(args.env, args.open)
        if args.command == "create-series":
            return cmd_create_series(args.env, args.name)
        if args.command == "create-game":
            return cmd_create_game(args.env, args.name, args.series)
        if args.command == "create-version":
            return cmd_create_version(args.env, args.game, args.name)
        if args.command == "import-txt":
            return cmd_import_txt(args.env, args.version, args.file)
        if args.command == "auto-import":
            return cmd_auto_import(args.env, args.dry_run)
        if args.command.startswith("rename-"):
            return cmd_rename(args.env, args.command.split("-", 1)[1],
                              args.id, args.name)
        if args.command == "add-alias":
            return cmd_add_alias(args.env, args.game, args.alias)
        if args.command == "prepare":
            return cmd_prepare(args.env, args.game, args.version,
                               args.series, args.open)
        if args.command == "import-files":
            return cmd_import_files(args.env, args.series, args.files)
    except ValidationError as e:
        print(f"校验失败: {e}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
