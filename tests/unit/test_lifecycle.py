# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("GWS_RUNNING_TESTS", "1")

from gws.lifecycle import can_transition, check_transition  # noqa: E402
from gws.validation import LIFECYCLE_ERROR, validate_status_transition  # noqa: E402


class TestLifecycle(unittest.TestCase):
    def test_legal_transitions(self):
        self.assertTrue(can_transition("active", "archived"))
        self.assertTrue(can_transition("active", "trashed"))
        self.assertTrue(can_transition("archived", "active"))
        self.assertTrue(can_transition("deprecated", "active"))

    def test_illegal_transitions(self):
        for cur, tgt in (("trashed", "active"), ("trashed", "archived"),
                         ("active", "bogus"), ("bogus", "active")):
            with self.assertRaises((ValueError, Exception)):
                check_transition(cur, tgt)

    def test_trashed_is_terminal(self):
        with self.assertRaises(ValueError):
            check_transition("trashed", "active")

    def test_validation_wraps_as_lifecycle_error(self):
        with self.assertRaises(Exception) as ctx:
            validate_status_transition("trashed", "active")
        self.assertEqual(getattr(ctx.exception, "kind", None), LIFECYCLE_ERROR)


if __name__ == "__main__":
    unittest.main()
