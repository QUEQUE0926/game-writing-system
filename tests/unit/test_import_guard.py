# -*- coding: utf-8 -*-
"""导入防线 import_guard：版本名相似提醒 + 同内容跨版本提醒。"""
import os
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.import_guard import _suspicious  # noqa: E402


class TestSuspiciousNames(unittest.TestCase):
    def test_typo_caught(self):
        # 用户拍板场景：已有「8月更新」，手误打成「8跟新」
        self.assertTrue(_suspicious("8月更新", "8跟新"))

    def test_exact_and_empty_not_suspicious(self):
        self.assertFalse(_suspicious("8月更新", "8月更新"))
        self.assertFalse(_suspicious("", "8月更新"))
        self.assertFalse(_suspicious("正式版", ""))

    def test_containment_caught(self):
        self.assertTrue(_suspicious("正式版", "正式版v2"))

    def test_unrelated_names_not_suspicious(self):
        self.assertFalse(_suspicious("正式版", "8月更新"))

    def test_digit_progression_not_suspicious(self):
        # V1→V2 是正常版本递进，差异全在数字上，不提醒
        self.assertFalse(_suspicious("V1.0", "V2.0"))
        self.assertFalse(_suspicious("v0.6.11", "v0.6.12"))


if __name__ == "__main__":
    unittest.main()
