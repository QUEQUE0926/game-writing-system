# -*- coding: utf-8 -*-
"""一键验收 verify（02_ENGINEERING_RULES §9）。

一次执行：
  1. Schema check         —— 全部期望表存在
  2. Migration test       —— 全新库迁移 + 幂等重放
  3. Unit tests
  4. Integration tests
  5. Golden Project
  6. Import smoke test
  7. DB integrity check   —— integrity_check + foreign_key_check

只有 ALL CHECKS PASSED 才算验收通过。测试一律使用 TEST 环境 + 临时目录，
绝不触碰生产数据。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import current_version, list_migrations, migrate  # noqa: E402

EXPECTED_TABLES = {
    "series", "games", "game_versions", "sources", "segments",
    "episodes", "episode_segments", "material_cards", "material_card_evidence",
    "inspiration_cards", "tags", "asset_tags", "cross_references",
    "usage_records", "projects", "project_assets", "claims", "claim_evidence",
    "articles", "audit_log", "schema_migrations",
}

_results: list[tuple[str, bool, str]] = []


def step(name: str):
    def deco(fn):
        def run():
            try:
                fn()
                _results.append((name, True, "OK"))
                print(f"  [PASS] {name}")
            except Exception as e:  # noqa: BLE001
                _results.append((name, False, str(e)))
                print(f"  [FAIL] {name}: {e}")
        return run
    return deco


@step("Schema check")
def schema_check():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GWS_DATA_ROOT"] = tmp
        cfg = load_config("test")
        conn = connect(cfg)
        try:
            migrate(conn)
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            missing = EXPECTED_TABLES - names
            if missing:
                raise AssertionError(f"缺少表: {missing}")
            # 迁移文件命名规范
            list_migrations()
        finally:
            conn.close()
            del os.environ["GWS_DATA_ROOT"]


@step("Migration test (fresh + idempotent)")
def migration_test():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GWS_DATA_ROOT"] = tmp
        conn = connect(load_config("test"))
        try:
            first = migrate(conn)
            second = migrate(conn)
            expected = list(range(1, len(list_migrations()) + 1))
            if first != expected or second != []:
                raise AssertionError(
                    f"迁移行为异常: first={first}, second={second}")
            if current_version(conn) != len(list_migrations()):
                raise AssertionError("schema version 与迁移文件数不一致")
        finally:
            conn.close()
            del os.environ["GWS_DATA_ROOT"]


@step("Unit tests")
def unit_tests():
    run_discover("tests/unit")


@step("Integration tests")
def integration_tests():
    run_discover("tests/integration")


@step("Golden Project")
def golden_tests():
    run_discover("tests/golden")


def run_discover(rel: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", rel,
         "-t", str(REPO_ROOT), "-v"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        env={**os.environ, "GWS_RUNNING_TESTS": "1",
             "PYTHONIOENCODING": "utf-8",
             "PYTHONPATH": str(REPO_ROOT / "src")},
        timeout=120,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise AssertionError(f"{rel} 失败:\n{tail}")


@step("Import smoke test (DEV, 非生产数据)")
def import_smoke():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GWS_DATA_ROOT"] = tmp
        cfg = load_config("dev")
        conn = connect(cfg)
        try:
            migrate(conn)
            from gws.ids import new_id
            game_id, ver_id = new_id(), new_id()
            conn.execute("INSERT INTO games (id, name) VALUES (?,?)",
                         (game_id, "Smoke Game"))
            conn.execute(
                "INSERT INTO game_versions (id, game_id, name) VALUES (?,?,?)",
                (ver_id, game_id, "ea"))
            conn.commit()
            txt = Path(tmp) / "smoke.txt"
            txt.write_text("[作者] 冒烟测试行。\n", encoding="utf-8")
            from gws.import_service import import_source
            r = import_source(cfg, ver_id, txt)
            if r["segments"] != 1 or r["dedup"]:
                raise AssertionError(f"导入结果异常: {r}")
        finally:
            conn.close()
            del os.environ["GWS_DATA_ROOT"]


@step("DB integrity check")
def integrity_check():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GWS_DATA_ROOT"] = tmp
        conn = connect(load_config("test"))
        try:
            migrate(conn)
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise AssertionError(f"integrity_check: {ok}")
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise AssertionError(f"foreign_key_check 违例: {violations}")
        finally:
            conn.close()
            del os.environ["GWS_DATA_ROOT"]


def main() -> int:
    print("=== gws verify ===")
    for fn in (schema_check, migration_test, unit_tests,
               integration_tests, golden_tests, import_smoke,
               integrity_check):
        print(f"--- {fn.__name__} ---")
        fn()
    failed = [r for r in _results if not r[1]]
    print("=== 结果 ===")
    for name, ok, msg in _results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {msg}"))
    if failed:
        print("FAILED")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
