# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.import_service import read_text_strict  # noqa: E402


class TestEncoding(unittest.TestCase):
    def test_utf8_strict(self):
        text, enc = read_text_strict("你好世界".encode("utf-8"))
        self.assertEqual((text, enc), ("你好世界", "utf-8"))

    def test_gbk_detected_not_mojibake(self):
        # GBK 字节必须被正确识别，不能被 errors=ignore 静默吃掉
        text, enc = read_text_strict("灰烬之国".encode("gbk"))
        self.assertEqual(enc, "gbk")
        self.assertIn("灰烬之国", text)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            read_text_strict(b"\xff\xfe\xfa\x81\x9c\x88")


if __name__ == "__main__":
    unittest.main()
