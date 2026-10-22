import copy
import unittest

from tgspipe.build import build_character
from tgspipe.validate import validate_doc
from examples_build import make_rig


def valid_doc():
    return build_character(make_rig())


class TestValidate(unittest.TestCase):
    def test_example_passes_all_gates(self):
        report = validate_doc(valid_doc(), size_bytes=4096)
        self.assertTrue(report.ok, [f.detail for f in report.errors])
        self.assertEqual(report.stats["loop"], "seamless")

    def test_wrong_canvas_fails(self):
        doc = valid_doc()
        doc["w"] = 256
        report = validate_doc(doc, size_bytes=1024)
        self.assertFalse(report.ok)
        self.assertIn("canvas", [f.rule for f in report.errors])

    def test_oversize_fails(self):
        report = validate_doc(valid_doc(), size_bytes=70 * 1024)
        self.assertIn("size", [f.rule for f in report.errors])

    def test_too_long_fails(self):
        doc = valid_doc()
        doc["op"] = 60 * 5
        report = validate_doc(doc, size_bytes=1024)
        self.assertIn("duration", [f.rule for f in report.errors])

    def test_forbidden_mask_fails(self):
        doc = valid_doc()
        doc["layers"][0]["masksProperties"] = []
        report = validate_doc(doc, size_bytes=1024)
        self.assertIn("forbidden", [f.rule for f in report.errors])

    def test_broken_loop_fails(self):
        doc = copy.deepcopy(valid_doc())
        for layer in doc["layers"]:
            r = layer["ks"].get("r")
            if isinstance(r, dict) and r.get("a") == 1:
                r["k"][-1]["s"] = 999
                break
        report = validate_doc(doc, size_bytes=1024)
        self.assertIn("loop-seam", [f.rule for f in report.errors])


if __name__ == "__main__":
    unittest.main()
