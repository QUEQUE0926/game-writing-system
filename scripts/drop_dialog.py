# -*- coding: utf-8 -*-
"""拖放导入弹窗：拖 txt 到 drop-import-*.bat 后弹出填写窗口。

流程：
1. 每个文件弹一窗，按现文件名预填 系列/游戏/版本；默认系列 = 游戏名（可改）。
2. 点「导入」→ 先查库弹"确认归档"预告（复用/新建/重复）→ 确认后把源文件
   **复制**（原名不动）到数据目录 inbox/drop-import/ 下，按规范名存放 → 入库。
3. 全部处理完显示导入结果窗口。

命名规范：系列 - 游戏 - 版本.txt（无系列则 游戏 - 版本.txt）。
"""
from __future__ import annotations

import hashlib
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import re

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# 预填时从游戏名/版本名尾部剥掉的常见标注（只影响弹窗预填，不影响解析规则）
_SUFFIX_RE = re.compile(
    r"[\s_\-]*(原文|实况|merged|录播|直播|全流程)[\s_]*$", re.IGNORECASE)


def _strip_suffix(s: str) -> str:
    return _SUFFIX_RE.sub("", s).strip()

from gws.auto_import import (  # noqa: E402
    _guard_warnings, _resolve_target, build_target_name, parse_stem)
from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.import_guard import cross_version_dup, version_name_suspects  # noqa: E402
from gws.import_service import import_source  # noqa: E402
from gws.migrations import migrate  # noqa: E402
from gws.repositories import (GameRepository, SeriesRepository,  # noqa: E402
                              VersionRepository)
from gws.validation import ValidationError  # noqa: E402


def _db_lookup(conn, sql: str, args: tuple):
    return conn.execute(sql, args).fetchone()


def preview_target(conn, path: Path, series: str, game: str,
                   version: str) -> list[str]:
    """提交前查库，生成归档预告（复用/新建/重复/冲突），一行一条。"""
    lines: list[str] = []
    explicit_series = bool(series) and series != game

    srow = _db_lookup(
        conn, "SELECT id FROM series WHERE name=? AND status!='trashed'",
        (series,))
    lines.append(f"系列《{series}》："
                 + ("已有，将归入该系列" if srow else "库中不存在，将新建"))

    grow = _db_lookup(
        conn, "SELECT id, name FROM games WHERE name=? AND status!='trashed'",
        (game,))
    if grow is None:
        arow = _db_lookup(
            conn,
            "SELECT g.id, g.name FROM games g "
            "JOIN game_aliases a ON a.game_id=g.id "
            "WHERE a.alias=? AND g.status!='trashed'", (game,))
        grow = arow
        if arow:
            lines.append(f"游戏《{game}》：是《{arow['name']}》的别名，"
                         "将归到同一档案")
    if explicit_series:
        if srow and grow and _db_lookup(
                conn, "SELECT id FROM games WHERE id=? AND series_id=?",
                (grow["id"], srow["id"])):
            lines.append(f"游戏《{game}》：该系列下已有同名游戏，将复用")
        elif srow:
            lines.append(f"游戏《{game}》：将在系列《{series}》下新建")
        else:
            lines.append(f"游戏《{game}》：将随系列一并新建")
    else:
        # 默认系列（系列名==游戏名）分支，对齐 _resolve_target：
        # 1) 若存在与游戏同名的系列 → 严格系列内匹配，不会冲突
        # 2) 否则全局匹配主名/别名：唯一命中复用，多命中⚠冲突，零命中新建
        same_series = _db_lookup(
            conn, "SELECT id FROM series WHERE name=? AND status!='trashed'",
            (game,))
        if same_series:
            grow = _db_lookup(
                conn, "SELECT id FROM games WHERE series_id=? AND name=? "
                "AND status!='trashed'", (same_series["id"], game))
            if grow:
                lines.append(f"游戏《{game}》：同名系列《{game}》下已有，"
                             "将复用（系列内匹配）")
            else:
                lines.append(f"游戏《{game}》：将在同名系列《{game}》下新建")
        else:
            cnt = conn.execute(
                "SELECT COUNT(*) c FROM games WHERE name=? "
                "AND status!='trashed'", (game,)).fetchone()["c"]
            acnt = conn.execute(
                "SELECT COUNT(*) c FROM game_aliases a JOIN games g "
                "ON g.id=a.game_id WHERE a.alias=? AND g.status!='trashed'",
                (game,)).fetchone()["c"]
            # 对齐 _resolve_target：先主名后别名，各自唯一才算命中
            if cnt > 1 or (cnt == 0 and acnt > 1):
                total = cnt if cnt > 1 else acnt
                lines.append(f"⚠ 库中有 {total} 个《{game}》"
                             "（分属不同系列），"
                             "默认系列无法确定归属，导入会报错；"
                             "请把系列名改成与游戏名不同的显式系列")
            elif cnt == 1 or acnt == 1:
                lines.append(f"游戏《{game}》：库中已有，将复用（不会新建）")
            else:
                lines.append(f"游戏《{game}》：库中不存在，将新建"
                             "（默认系列=游戏名）")
    if grow is None:
        grow = _db_lookup(
            conn, "SELECT id FROM games WHERE name=? AND status!='trashed'",
            (game,))
    if grow is None:
        grow = _db_lookup(
            conn, "SELECT g.id FROM games g JOIN game_aliases a "
            "ON a.game_id=g.id WHERE a.alias=? AND g.status!='trashed'",
            (game,))
    if grow is None:
        lines.append(f"版本《{version}》：将随新建的游戏一并新建")
        return lines
    if grow:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        vrow = _db_lookup(
            conn,
            "SELECT id FROM game_versions WHERE game_id=? AND name=? "
            "AND status!='trashed'", (grow["id"], version))
        if vrow:
            lines.append(f"版本《{version}》：该游戏下已有，将归入")
            dup = _db_lookup(
                conn, "SELECT id FROM sources WHERE version_id=? AND sha256=?",
                (vrow["id"], sha))
            if dup:
                lines.append("⚠ 内容与该版本已有实况完全相同 → 导入时将自动"
                             "跳过（不会存两份）")
            else:
                lines.append("内容为新的实况 → 将作为一条新实况存入"
                             "（撞名自动标 #2、#3）")
        else:
            lines.append(f"版本《{version}》：该游戏下不存在，将新建")
            sus = version_name_suspects(conn, grow["id"], version)
            if sus:
                lines.append("⚠ 现有版本"
                             + "、".join(f"《{s}》" for s in sus)
                             + "与新名字很像，确定不是手误？")
        others = cross_version_dup(conn, grow["id"], sha,
                                   exclude_version_id=vrow["id"]
                                   if vrow else None)
        if others:
            lines.append("⚠ 内容与该游戏另一版本"
                         + "、".join(f"《{o}》" for o in others)
                         + "的实况完全相同，可能重复导入")
    return lines


def ask_one(root: tk.Tk, path: Path, conn=None) -> dict | None:
    """弹窗收集一个文件的信息。返回 None 表示用户跳过。"""
    stem_series, game, version = parse_stem(path.stem)
    game = _strip_suffix(game)
    version = _strip_suffix(version)
    win = tk.Toplevel(root)
    win.title(f"导入信息 — {path.name}")
    win.grab_set()
    win.resizable(False, False)

    frm = ttk.Frame(win, padding=12)
    frm.grid()
    vars_ = {
        "series": tk.StringVar(value=stem_series or game),
        "game": tk.StringVar(value=game),
        "version": tk.StringVar(value=version),
    }
    rows = [("系列（默认=游戏名）", "series"),
            ("游戏名", "game"),
            ("版本名", "version")]
    for i, (label, key) in enumerate(rows):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=3)
        ttk.Entry(frm, width=38, textvariable=vars_[key]).grid(
            row=i, column=1, pady=3)
    ttk.Label(frm, text="目标名:", foreground="#888").grid(
        row=3, column=0, sticky="w")
    target_lbl = ttk.Label(frm, text="", foreground="#0a7")
    target_lbl.grid(row=3, column=1, sticky="w")

    def refresh_target(*_):
        target_lbl.config(text=build_target_name(
            vars_["series"].get(), vars_["game"].get(),
            vars_["version"].get()))
    for v in vars_.values():
        v.trace_add("write", refresh_target)
    refresh_target()

    # 实时查询区：输入停顿 ~400ms 后自动查库，显示 复用/新建/重复/冲突
    status_lbl = ttk.Label(frm, text="库内查询：…", foreground="#888",
                           justify="left", wraplength=430)
    status_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
    status_job = {"after": None}

    def refresh_status(*_):
        if conn is None or not win.winfo_exists():
            return
        series_v = vars_["series"].get().strip() or vars_["game"].get().strip()
        game_v = vars_["game"].get().strip()
        version_v = vars_["version"].get().strip()
        if not game_v or not version_v:
            status_lbl.config(text="库内查询：游戏名/版本名不能为空",
                              foreground="#b00")
            return
        try:
            msgs = preview_target(conn, path, series_v, game_v, version_v)
        except Exception as e:  # noqa: BLE001
            status_lbl.config(text=f"库内查询失败: {e}", foreground="#b00")
            return
        warn = any(m.startswith("⚠") for m in msgs)
        status_lbl.config(text="库内查询：\n" + "\n".join(msgs),
                          foreground="#b00" if warn else "#060")

    def schedule_status(*_):
        if status_job["after"]:
            win.after_cancel(status_job["after"])
        status_lbl.config(text="库内查询：…", foreground="#888")
        status_job["after"] = win.after(400, refresh_status)

    for v in vars_.values():
        v.trace_add("write", schedule_status)
    schedule_status()

    result: dict | None = None

    def on_ok():
        nonlocal result
        series_v = vars_["series"].get().strip()
        game_v = vars_["game"].get().strip()
        version_v = vars_["version"].get().strip()
        if not game_v or not version_v:
            messagebox.showwarning("信息不全", "游戏名和版本名不能为空。",
                                   parent=win)
            return
        # 提交前预告：查库告诉用户复用/新建/重复/冲突
        if conn is not None:
            try:
                msgs = preview_target(conn, path,
                                      series_v or game_v, game_v, version_v)
            except Exception as e:  # noqa: BLE001
                messagebox.showwarning("预检失败", f"{e}", parent=win)
                return
            ok = messagebox.askyesno(
                "确认归档",
                "文件：" + path.name + "\n（源文件不会被改动，"
                "将复制一份到系统数据目录）\n\n" + "\n".join(msgs)
                + "\n\n确认按此导入吗？",
                parent=win)
            if not ok:
                return  # 留在窗口继续改
        result = {"series": series_v, "game": game_v, "version": version_v}
        win.destroy()

    def on_skip():
        win.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=5, column=0, columnspan=2, pady=(10, 0))
    ttk.Button(btns, text="导入", command=on_ok).pack(side="left", padx=4)
    ttk.Button(btns, text="跳过此文件", command=on_skip).pack(side="left", padx=4)
    win.protocol("WM_DELETE_WINDOW", on_skip)
    win.wait_window()
    return result


def import_one(cfg, conn, path: Path, series: str, game: str,
               version: str) -> dict:
    """按弹窗确认的信息建档并导入单个文件。

    系列==游戏名视为"默认系列"，走 _resolve_target 的全局匹配
    （游戏改过名/有别名时仍能归到同一档案）；显式改过的系列严格系列内匹配。
    """
    versions = VersionRepository(conn, cfg)
    explicit_series = bool(series) and series != game
    series_id, game_id = _resolve_target(
        conn, cfg, series or game, game, version, explicit_series)
    row = conn.execute(
        "SELECT name FROM games WHERE id=?", (game_id,)).fetchone()
    actual_game = row["name"]
    ver_row = conn.execute(
        "SELECT id FROM game_versions WHERE game_id=? AND name=? "
        "AND status!='trashed' LIMIT 1", (game_id, version)).fetchone()
    warnings = _guard_warnings(
        conn, game_id, version,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        ver_row["id"] if ver_row else None)
    ver_id = ver_row["id"] if ver_row else versions.create(game_id, version)
    r = import_source(cfg, ver_id, path)
    return {"file": path.name, "series": series, "game": actual_game,
            "version": version, "source_id": r["source_id"],
            "segments": r["segments"], "dedup": r["dedup"],
            "warnings": warnings}


def _discard_copy(target: Path, lines: list[str]) -> None:
    """导入成功后删掉 drop-import 里的副本（原文已归档 raw/，源文件未动）。"""
    try:
        target.unlink(missing_ok=True)
        lines.append("    副本已清理（inbox/drop-import/），源文件未动")
    except OSError as e:
        lines.append(f"    ⚠ 副本删除失败（{e}），可手动清理 "
                     f"{target}")


def main() -> int:
    files = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]
    root = tk.Tk()
    root.withdraw()
    if not files:
        messagebox.showinfo("拖放导入", "没有检测到 txt 文件。")
        return 0

    pending: list[Path] = []
    used_targets: set[str] = set()  # 同批次目标名去重（同版本多实况）
    cfg = load_config(os.environ.get("GWS_ENV", "dev"))
    conn = connect(cfg)
    migrate(conn)
    cfg.ensure_dirs()
    # 副本统一落在这里，源文件永远不动
    inbox_drop = cfg.inbox_dir / "drop-import"
    inbox_drop.mkdir(parents=True, exist_ok=True)

    def copy_to_inbox(f: Path, info: dict) -> Path:
        """复制源文件到 inbox/drop-import/<规范名>.txt，撞名自动 #2/#3。"""
        src_sha = hashlib.sha256(f.read_bytes()).hexdigest()

        def same_content(p: Path) -> bool:
            try:
                return hashlib.sha256(p.read_bytes()).hexdigest() == src_sha
            except OSError:
                return False

        dest = inbox_drop / build_target_name(
            info["series"], info["game"], info["version"])
        taken = {p.name for p in pending} | used_targets
        if dest.name in taken or (dest.exists() and not same_content(dest)):
            k = 2
            while True:
                cand = inbox_drop / build_target_name(
                    info["series"], info["game"], info["version"], take=k)
                if not (cand.name in taken
                        or (cand.exists() and not same_content(cand))):
                    dest = cand
                    break
                k += 1
                if k > 999:
                    break
        # 同名且同内容的副本已存在 → 直接复用，不重复复制
        if not dest.exists():
            import shutil
            shutil.copy2(f, dest)
        used_targets.add(dest.name)
        return dest

    for f in files:
        info = ask_one(root, f, conn=conn)
        if info is None:
            continue
        try:
            target = copy_to_inbox(f, info)
        except OSError as e:
            messagebox.showwarning(
                "复制失败", f"{f.name} 复制到数据目录失败（{e}），已跳过。")
            continue
        pending.append(target)

    if not pending:
        conn.close()
        return 0

    lines: list[str] = []
    try:
        for target in pending:
            stem_series, game, version = parse_stem(target.stem)
            try:
                r = import_one(cfg, conn, target, stem_series or game,
                               game, version)
                tag = "去重跳过（已导入过）" if r["dedup"] \
                    else f"新增 {r['segments']} 个 Segment（原文已归档到 raw/）"
                lines.append(f"✔ {r['file']}  →  系列[{r['series']}] "
                             f"游戏[{r['game']}] 版本[{r['version']}]\n    {tag}")
                for w in r.get("warnings") or []:
                    lines.append(f"    ⚠ {w}")
                _discard_copy(target, lines)
            except ValidationError as e:
                lines.append(f"✘ {target.name}\n    校验失败: {e}"
                             "\n    （副本保留在 drop-import/，源文件未动）")
            except Exception as e:  # noqa: BLE001
                lines.append(f"✘ {target.name}\n    失败: {e}"
                             "\n    （副本保留在 drop-import/，源文件未动）")
    finally:
        conn.close()

    # 结果窗口
    res = tk.Toplevel(root)
    res.title("导入结果")
    txt = tk.Text(res, width=72, height=min(6 + 2 * len(lines), 30))
    txt.pack(padx=10, pady=10)
    txt.insert("1.0", "\n".join(lines))
    txt.config(state="disabled")

    def close_all():
        root.destroy()
    ttk.Button(res, text="完成", command=close_all).pack(pady=(0, 10))
    res.grab_set()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
