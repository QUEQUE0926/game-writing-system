# -*- coding: utf-8 -*-
"""自动导入 v2：扫描 inbox/auto/，按目录与文件名自动建档。

目录约定：
    inbox/auto/游戏名 - 版本.txt               → 无系列
    inbox/auto/系列名/游戏名 - 版本.txt         → 挂到该系列
    inbox/auto/系列名/游戏名.txt               → 版本默认 default
    分隔符支持 " - " / "--" / "——"

匹配规则（绝不跨系列猜测）：
    系列按文件夹名精确匹配（不存在则建）；
    游戏在「该文件所属系列」内按 主名 → 别名 匹配（别名见 game_aliases 表），
    都不中才新建。
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from .config import Config
from .import_guard import cross_version_dup, version_name_suspects
from .import_service import import_source
from .repositories import GameRepository, SeriesRepository, VersionRepository

_SPLIT_RE = re.compile(r"\s*(?:--|——|—-|－{1,2}|—)\s*")
_DASH_SPLIT_RE = re.compile(r"\s+-\s+")  # " - " 分段符
# 实况序号：文件名结尾的 "#2" "#3"…（同游戏同版本多份实况的区分标记，
# 导入时剥离，全部归入同一版本；#1 等价于无序号）
_TAKE_RE = re.compile(r"\s*#(\d+)\s*$")


def build_target_name(series: str | None, game: str, version: str,
                      take: int = 0) -> str:
    """按命名规范生成目标文件名（含扩展名）。

    有系列 → 系列 - 游戏 - 版本.txt；无系列 → 游戏 - 版本.txt。
    take >= 2 时追加 " #N" 实况序号。
    """
    version = (version or "").strip() or "default"
    if series and series.strip():
        base = f"{series.strip()} - {game.strip()} - {version}"
    else:
        base = f"{game.strip()} - {version}"
    if take >= 2:
        base = f"{base} #{take}"
    return f"{base}.txt"


def split_take(stem: str) -> tuple[str, int]:
    """剥离结尾的实况序号 "#N"（N>=2 才有意义，全部剥掉统一处理）。

    返回 (剩余 stem, 序号)；无序号时序号为 1。
    """
    m = _TAKE_RE.search(stem)
    if m:
        return stem[:m.start()].strip(), max(1, int(m.group(1)))
    return stem, 1


def parse_stem(stem: str) -> tuple[str | None, str, str]:
    """从文件名解析 (series|None, game, version)。

    分段符：" - "（推荐）、"--"、"——"。
    - 1 段：游戏，版本 default
    - 2 段：游戏 - 版本
    - 3 段及以上：系列 - 游戏 - 版本（第 3 段之后并入版本，允许版本名带 - 之外的内容）
    结尾的实况序号 "#N"（如 "灰烬之国 - demo #2"）先剥离，不影响解析结果。
    """
    stem, _ = split_take(stem)
    strict = [p.strip() for p in _SPLIT_RE.split(stem.strip()) if p.strip()]
    if len(strict) == 1:
        loose = _DASH_SPLIT_RE.split(stem.strip())
        loose = [p.strip() for p in loose if p.strip()]
        if len(loose) >= 3:
            return loose[0], loose[1], "-".join(loose[2:])
        if len(loose) == 2:
            return None, loose[0], loose[1]
        return None, stem.strip(), "default"
    if len(strict) == 2:
        return None, strict[0], strict[1]
    return strict[0], strict[1], "-".join(strict[2:])


def parse_filename(stem: str) -> tuple[str, str]:
    """兼容旧接口：(game, version)。"""
    _, game, ver = parse_stem(stem)
    return game, ver


def scan_inbox(cfg: Config) -> list[tuple[str | None, Path]]:
    """返回 [(series_name|None, txt路径)]。

    inbox/auto/*.txt → 无系列；inbox/auto/<子文件夹>/*.txt → 挂该系列。
    """
    auto_dir = cfg.inbox_dir / "auto"
    auto_dir.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str | None, Path]] = []
    for p in sorted(auto_dir.glob("*.txt")):
        if p.is_file():
            out.append((None, p))
    for d in sorted(p for p in auto_dir.iterdir() if p.is_dir()):
        for p in sorted(d.glob("*.txt")):
            if p.is_file():
                out.append((d.name, p))
    return out


def _find_series(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM series WHERE name=? AND status!='trashed' LIMIT 1",
        (name,)).fetchone()
    return row["id"] if row else None


def _find_version(conn: sqlite3.Connection, game_id: str,
                  name: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM game_versions WHERE game_id=? AND name=? "
        "AND status!='trashed' LIMIT 1", (game_id, name)).fetchone()
    return row["id"] if row else None


def _resolve_target(conn: sqlite3.Connection, cfg: Config,
                    series_name: str, game_name: str, ver_name: str,
                    explicit_series: bool) -> tuple[str, str]:
    """解析/建档 (series_id, game_id)。

    显式系列（三段文件名 / 文件夹 / --series）：严格系列内匹配（主名→别名）。
    默认系列（系列=游戏名兜底）：先找同名系列；找不到则跨系列全局匹配一次——
    唯一命中就复用该档案（含其系列），多个命中报错，零命中新建默认系列档案。
    """
    games = GameRepository(conn, cfg)
    if explicit_series:
        series_id = _find_series(conn, series_name) \
            or SeriesRepository(conn, cfg).create(series_name)
        game_id = games.find_by_name_or_alias(game_name, series_id) \
            or games.create(game_name, series_id)
        return series_id, game_id

    # 默认系列场景
    series_id = _find_series(conn, series_name)
    if series_id is not None:
        game_id = games.find_by_name_or_alias(game_name, series_id)
        if game_id is not None:
            return series_id, game_id
    # 同名系列不存在，或系列内没匹配到 → 全局按名字/别名找
    hits = games.find_global(game_name)
    if len(hits) == 1:
        return _game_series(conn, cfg, hits[0]), hits[0]
    if len(hits) > 1:
        raise ValueError(
            f"游戏名/别名 {game_name!r} 命中多个档案，请在文件名第三段"
            f"或文件夹中显式写系列名以消歧：{hits}")
    # 零命中 → 新建默认系列档案
    series_id = series_id or SeriesRepository(conn, cfg).create(series_name)
    return series_id, games.create(game_name, series_id)


def _game_series(conn: sqlite3.Connection, cfg: Config, game_id: str) -> str:
    """取游戏所属系列；理论上必有（默认系列约定），兜底建同名系列。"""
    row = conn.execute(
        "SELECT series_id, name FROM games WHERE id=?", (game_id,)).fetchone()
    if row and row["series_id"]:
        return row["series_id"]
    return SeriesRepository(conn, cfg).create(row["name"])


def _guard_warnings(conn: sqlite3.Connection, game_id: str, ver_name: str,
                    sha: str, ver_id: str | None) -> list[str]:
    """导入防线①②（import_guard）：版本名相似 + 同内容跨版本，只提醒不拦截。"""
    warnings = []
    if ver_id is None:
        sus = version_name_suspects(conn, game_id, ver_name)
        if sus:
            warnings.append(
                "版本名《{}》与现有版本{}名字很像，若是手误请改名后再导"
                "（本次已按新名字建档）".format(
                    ver_name, "、".join(f"《{s}》" for s in sus)))
    dups = cross_version_dup(conn, game_id, sha, exclude_version_id=ver_id)
    if dups:
        warnings.append(
            "文件内容与该游戏版本{}的实况完全相同，可能重复导入".format(
                "、".join(f"《{d}》" for d in dups)))
    return warnings


def import_files(cfg: Config, conn: sqlite3.Connection, paths: list[str],
                 series: str | None = None) -> dict:
    """导入任意路径的 txt（拖放入口用）。文件名解析规则与 auto_import 相同。

    系列来源优先级：--series 参数 > 文件名第三段。
    """
    results: list[dict] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            results.append({"file": str(raw), "error": "文件不存在"})
            continue
        if path.suffix.lower() != ".txt":
            results.append({"file": path.name, "error": "只支持 .txt"})
            continue
        stem_series, game_name, ver_name = parse_stem(path.stem)
        # 系列默认 = 游戏名（每个游戏自带同名系列；显式指定的系列优先）
        explicit = series is not None or stem_series is not None
        series_name = series or stem_series or game_name
        series_id, game_id = _resolve_target(
            conn, cfg, series_name, game_name, ver_name, explicit)
        # 全局匹配可能命中已有档案，系列/游戏的真实名以库为准
        names = conn.execute(
            "SELECT (SELECT name FROM series WHERE id=?), "
            "(SELECT name FROM games WHERE id=?)", (series_id, game_id)).fetchone()
        ver_id = _find_version(conn, game_id, ver_name)
        warnings = _guard_warnings(
            conn, game_id, ver_name,
            hashlib.sha256(path.read_bytes()).hexdigest(), ver_id)
        if ver_id is None:
            ver_id = VersionRepository(conn, cfg).create(game_id, ver_name)
        r = import_source(cfg, ver_id, path)
        results.append({"file": path.name, "series": names[0],
                        "game": names[1], "version": ver_name,
                        "game_id": game_id, "version_id": ver_id,
                        "source_id": r["source_id"],
                        "segments": r["segments"], "dedup": r["dedup"],
                        "warnings": warnings})
    return {"dry_run": False, "results": results}


def auto_import(cfg: Config, conn: sqlite3.Connection,
                dry_run: bool = False) -> dict:
    """扫描并导入 inbox/auto/ 下全部 txt。返回摘要（含 dry_run 预览）。"""
    versions = VersionRepository(conn, cfg)

    plan: list[dict] = []
    for folder_series, path in scan_inbox(cfg):
        stem_series, game_name, ver_name = parse_stem(path.stem)
        if folder_series is not None:
            # 文件夹是系列权威来源；文件名里也写了系列则必须一致
            if stem_series is not None and stem_series != folder_series:
                raise ValueError(
                    f"{path.name}: 文件名系列[{stem_series}]与文件夹"
                    f"[{folder_series}]不一致，请修正后重试")
            series_name = folder_series
        else:
            series_name = stem_series
        plan.append({"file": path.name, "series": series_name,
                     "game": game_name, "version": ver_name, "path": path})

    if dry_run:
        return {"dry_run": True, "plan": [
            {k: v for k, v in p.items() if k != "path"} for p in plan]}

    results: list[dict] = []
    for p in plan:
        # 边处理边查：同批次先建的档对后续文件可见
        explicit = p["series"] is not None
        if p["series"] is None:
            p["series"] = p["game"]  # 系列默认 = 游戏名
        series_id, game_id = _resolve_target(
            conn, cfg, p["series"], p["game"], p["version"], explicit)
        names = conn.execute(
            "SELECT (SELECT name FROM series WHERE id=?), "
            "(SELECT name FROM games WHERE id=?)", (series_id, game_id)).fetchone()
        ver_id = _find_version(conn, game_id, p["version"])
        warnings = _guard_warnings(
            conn, game_id, p["version"],
            hashlib.sha256(p["path"].read_bytes()).hexdigest(), ver_id)
        if ver_id is None:
            ver_id = versions.create(game_id, p["version"])
        r = import_source(cfg, ver_id, p["path"])
        results.append({**{k: v for k, v in p.items() if k != "path"},
                        "series": names[0], "game": names[1],
                        "game_id": game_id, "version_id": ver_id,
                        "source_id": r["source_id"],
                        "segments": r["segments"], "dedup": r["dedup"],
                        "warnings": warnings})
    return {"dry_run": False, "results": results}
