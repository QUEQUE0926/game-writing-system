# -*- coding: utf-8 -*-
"""Validation 层 v0（11_VALIDATION_SPEC）。

写入顺序：Model Output → Schema Validation → Reference Validation
         → Domain Validation → Transaction → Database。

本模块覆盖：
- Reference Error：引用目标不存在
- Lifecycle Error：trashed 对象被作为正常引用目标 / 非法状态流转
- 事务封装：Validate → BEGIN → Write → COMMIT；失败 ROLLBACK
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from .lifecycle import check_transition

# 领域校验错误类型（11 号文档的必查错误子集，v0）
REFERENCE_ERROR = "REFERENCE_ERROR"
LIFECYCLE_ERROR = "LIFECYCLE_ERROR"


class ValidationError(Exception):
    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(f"[{kind}] {message}")


def validate_reference_target(conn: sqlite3.Connection, table: str,
                              object_id: str, field: str) -> None:
    """引用校验：目标必须存在，且不得是 trashed（Lifecycle Error）。"""
    row = conn.execute(
        f"SELECT id, status FROM {table} WHERE id = ?", (object_id,)
    ).fetchone()
    if row is None:
        raise ValidationError(REFERENCE_ERROR,
                              f"{field} 指向不存在的 {table}.{object_id}")
    if row["status"] == "trashed":
        raise ValidationError(
            LIFECYCLE_ERROR,
            f"{field} 指向已 trashed 的 {table}.{object_id}，"
            "trashed 对象不能接收新的正常引用")


def validate_status_transition(current: str, target: str) -> None:
    try:
        check_transition(current, target)
    except ValueError as e:
        raise ValidationError(LIFECYCLE_ERROR, str(e)) from e


def in_transaction(conn: sqlite3.Connection, fn: Callable[[], None]) -> None:
    """Validate → BEGIN → Write → COMMIT；失败 ROLLBACK（02 §4）。"""
    try:
        conn.execute("BEGIN")
        fn()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
