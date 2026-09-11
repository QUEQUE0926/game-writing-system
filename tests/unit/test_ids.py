# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.ids import is_valid_stable_id, new_id  # noqa: E402


class TestIds(unittest.TestCase):
    def test_id_format_and_uniqueness(self):
        ids = {new_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000, "ID 必须唯一，永不复用")
        for i in list(ids)[:100]:
            self.assertTrue(is_valid_stable_id(i))

    def test_ids_are_time_ordered(self):
        a, b = new_id(), new_id()
        self.assertLess(a, b, "UUIDv7 应随时间单调可排序")

    def test_invalid_ids_rejected(self):
        for bad in ("", "abc", "not-a-uuid", "550e8400-e29b-41d4-a716-446655440000"):
            self.assertFalse(is_valid_stable_id(bad))


if __name__ == "__main__":
    unittest.main()
