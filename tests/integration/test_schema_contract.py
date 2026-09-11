# -*- coding: utf-8 -*-
"""结构快照测试（轻量 Schema Contract）。

把每张表的列名逐个钉死在这里。任何"顺手改名"（如 judgement→judgment）
都会让本测试 FAIL，从而挡在 verify 门禁里。
新增列 = 在 EXPECTED_COLUMNS 里补一行；重命名列 = 禁止（见 AGENTS.md）。
"""
import os
import tempfile
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.config import load_config  # noqa: E402
from gws.db import connect  # noqa: E402
from gws.migrations import migrate  # noqa: E402

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "series": {"id", "name", "status", "created_at"},
    "games": {"id", "series_id", "name", "status", "created_at"},
    "game_versions": {"id", "game_id", "name", "status", "created_at",
                      "sort_key"},
    "sources": {"id", "version_id", "filename", "relative_path", "source_type",
                "sha256", "encoding", "status", "imported_at"},
    "segments": {"id", "source_id", "ordinal", "line_start", "line_end",
                 "speaker", "content_type", "text", "status", "created_at"},
    "episodes": {"id", "version_id", "title", "summary", "status", "created_at"},
    "episode_segments": {"episode_id", "segment_id", "ordinal", "position"},
    "material_cards": {"id", "episode_id", "subject", "observation",
                       "experience", "possible_cause", "interpretation",
                       "judgement", "quote", "evidence_strength",
                       "writing_value", "author_interest", "reuse_value",
                       "status", "created_at"},
    "material_card_evidence": {"material_card_id", "segment_id"},
    "inspiration_cards": {"id", "title", "content", "source_type",
                          "source_ref", "status", "created_at"},
    "tags": {"id", "name", "category", "status"},
    "asset_tags": {"tag_id", "asset_type", "asset_id"},
    "cross_references": {"id", "from_type", "from_id", "to_type", "to_id",
                         "ref_type", "status", "created_at"},
    "usage_records": {"id", "asset_type", "asset_id", "consumer_type",
                      "consumer_id", "role", "result", "created_at"},
    "projects": {"id", "title", "note", "status", "created_at"},
    "project_assets": {"project_id", "asset_type", "asset_id"},
    "claims": {"id", "project_id", "statement", "status", "created_at"},
    "claim_evidence": {"claim_id", "material_card_id"},
    "articles": {"id", "project_id", "topic", "outline", "draft",
                 "manuscript", "status", "created_at"},
    "audit_log": {"id", "event_name", "entity_type", "entity_id",
                  "detail", "created_at"},
    "game_aliases": {"id", "game_id", "alias", "created_at"},
    "schema_migrations": {"version", "name", "applied_at"},
}

# Level A 冻结索引：一旦存在就不许消失/改名（迁移 003）
EXPECTED_INDEXES = {
    "ux_games_series_name",
    "ux_games_standalone_name",
    "ux_episode_segments_position",
}


class TestSchemaSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GWS_DATA_ROOT"] = self.tmp.name
        self.conn = connect(load_config("test"))
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        del os.environ["GWS_DATA_ROOT"]
        self.tmp.cleanup()

    def test_all_expected_tables_exist(self):
        names = {r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(EXPECTED_COLUMNS) - names
        self.assertFalse(missing, f"缺失表: {missing}")

    def test_columns_match_snapshot(self):
        """列名逐表比对：少了（被改名/删除）或表消失都直接 FAIL。"""
        problems: list[str] = []
        for table, expected in EXPECTED_COLUMNS.items():
            actual = {r["name"] for r in self.conn.execute(
                f"PRAGMA table_info({table})")}
            if not actual:
                problems.append(f"{table}: 表不存在")
                continue
            missing = expected - actual
            extra = actual - expected
            if missing:
                problems.append(f"{table}: 缺失列 {sorted(missing)}（疑似被改名，"
                                "违反 AGENTS.md Level A 冻结规则）")
            if extra:
                problems.append(f"{table}: 新增列 {sorted(extra)}"
                                "（若是合法扩展，请同步更新本快照）")
        self.assertFalse(problems, "\n".join(problems))

    def test_frozen_indexes_exist(self):
        names = {r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        missing = EXPECTED_INDEXES - names
        self.assertFalse(missing, f"缺失冻结索引: {missing}")


if __name__ == "__main__":
    unittest.main()
