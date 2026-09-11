# -*- coding: utf-8 -*-
"""稳定 ID 生成。

规则（00_OVERVIEW §19 / 03_DATA_MODEL）：
- 内部主键使用 UUIDv7 / ULID 风格稳定 ID；ID 一经签发永不复用。
- 展示名与 ID 分离。

这里实现 UUIDv7（时间有序，48bit 毫秒时间戳 + 随机位），方便按 ID 排序即按时间排序。
"""
from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ts = 0
_seq = 0


def new_id() -> str:
    """生成 UUIDv7 风格字符串（标准 36 字符带连字符）。

    同一毫秒内使用递增序列占满 ver 位，保证全局单调可排序；
    序列回绕时等待到下一毫秒。
    """
    global _last_ts, _seq
    with _lock:
        ts_ms = time.time_ns() // 1_000_000
        if ts_ms <= _last_ts:
            _seq += 1
            if _seq > 0x0FFF:  # 12-bit 序列回绕：等到下一毫秒
                while ts_ms <= _last_ts:
                    ts_ms = time.time_ns() // 1_000_000
                _seq = 0
            ts_ms = _last_ts
        else:
            _seq = 0
        _last_ts = ts_ms

        rand_a = _seq & 0x0FFF  # 12 bits (ver=7 占 4 bits，见下)
        rand_b = int.from_bytes(os.urandom(8), "big")
        rand_b = (rand_b & 0x3FFFFFFFFFFFFFFF) | 0x8000000000000000  # variant 10xx

        value = (ts_ms & 0xFFFFFFFFFFFF) << 80
        value |= 0x7 << 76            # version 7
        value |= rand_a << 64
        value |= rand_b
        return str(uuid.UUID(int=value))


def is_valid_stable_id(value: str) -> bool:
    """校验是否为系统签发的稳定 ID 格式（UUID 且 version=7）。"""
    try:
        u = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return u.version == 7
