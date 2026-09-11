# -*- coding: utf-8 -*-
"""生命周期状态机（03_DATA_MODEL / 00_OVERVIEW §19）。

状态：active / archived / deprecated / trashed（软删除优先）。
规则：
- trashed 是终点，不可复活（纠错用 replaced_by / 重新建档解决）。
- 非法流转直接抛错，不允许静默改库。
"""
from __future__ import annotations

STATUSES = ("active", "archived", "deprecated", "trashed")

TRANSITIONS: dict[str, set[str]] = {
    "active": {"archived", "deprecated", "trashed"},
    "archived": {"active", "trashed"},
    "deprecated": {"active", "trashed"},
    "trashed": set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def check_transition(current: str, target: str) -> None:
    if current not in STATUSES:
        raise ValueError(f"未知生命周期状态: {current!r}")
    if target not in STATUSES:
        raise ValueError(f"未知生命周期状态: {target!r}")
    if not can_transition(current, target):
        raise ValueError(
            f"非法生命周期流转: {current} → {target}（trashed 为终点，不可复活）")
