# -*- coding: utf-8 -*-
"""最小导入服务（04_SOURCE_PIPELINE 的 v0 切片）。

只覆盖 MVP 冒烟链路：merged TXT → Source → Segment（按行分块）。
- 编码探测：utf-8 → gbk → gb18030（strict 探测，避免静默丢字节）
- sha256 指纹，用于幂等导入（同 Version 下同 sha256 不重复导入）
- Raw 原文按 sha256 存档，永不覆盖、不被模型修改
只支持 .txt（用户明确：不导入 docx）。
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from .config import Config
from .db import connect
from .ids import new_id
from .migrations import migrate

_ENCODING_ORDER = ("utf-8", "gbk", "gb18030")


def read_text_strict(raw: bytes) -> tuple[str, str]:
    """strict 探测编码并解码；命中后返回 (text, encoding)。"""
    for enc in _ENCODING_ORDER:
        try:
            return raw.decode(enc, "strict"), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码（已尝试 utf-8/gbk/gb18030）")


def import_source(cfg: Config, version_id: str, txt_path: Path,
                  source_type: str = "merged_txt") -> dict:
    """导入一个 TXT 为 Source，并生成逐行 Segment。返回摘要 dict。"""
    txt_path = Path(txt_path)
    if txt_path.suffix.lower() != ".txt":
        raise ValueError(f"只支持 .txt 文件: {txt_path.name}")
    raw = txt_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text, encoding = read_text_strict(raw)

    # 幂等：同 Version + sha256 已存在则直接返回
    conn = connect(cfg)
    try:
        existing = conn.execute(
            "SELECT id FROM sources WHERE version_id=? AND sha256=?",
            (version_id, sha),
        ).fetchone()
        if existing:
            return {"source_id": existing["id"], "segments": None, "dedup": True}

        # Raw 存档（原始字节原样归档，不被覆盖；同 sha256 已有归档则复用）
        cfg.ensure_dirs()
        raw_dir = cfg.raw_dir / sha[:2]
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{sha}.txt"
        if not raw_path.exists():
            shutil.copyfile(txt_path, raw_path)

        source_id = new_id()
        rel = str(raw_path.relative_to(cfg.data_root)).replace("\\", "/")
        conn.execute(
            """INSERT INTO sources
               (id, version_id, filename, relative_path, source_type, sha256, encoding)
               VALUES (?,?,?,?,?,?,?)""",
            (source_id, version_id, txt_path.name, rel, source_type, sha, encoding),
        )

        lines = text.splitlines()
        n = 0
        for ordinal, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            conn.execute(
                """INSERT INTO segments
                   (id, source_id, ordinal, line_start, line_end, speaker, text)
                   VALUES (?,?,?,?,?,?,?)""",
                (new_id(), source_id, ordinal, ordinal, ordinal,
                 "unknown", stripped),
            )
            n += 1
        conn.commit()
        return {"source_id": source_id, "segments": n, "dedup": False}
    finally:
        conn.close()
