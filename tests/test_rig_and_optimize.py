import unittest

from tgspipe.build import Part, Rig, bezier_path, build_character, fill
from tgspipe.lottieio import dump_tgs, load_tgs
from tgspipe.optimize import optimize_doc
from tgspipe.validate import validate_doc
from examples_build import make_rig


class TestRig(unittest.TestCase):
    def test_audit_passes_for_example(self):
        self.assertEqual(make_rig().audit(), [])

    def test_audit_catches_bad_pivot(self):
        pts = [(0, 0), (40, 0), (40, 40), (0, 40)]
        part = Part(name="bad", items=[bezier_path(pts), fill("#FFFFFF")],
                    pivot=(900, 900), pos=(256, 256))
        problems = Rig(name="x", parts=[part]).audit()
        self.assertTrue(any("pivot" in p for p in problems))

    def test_audit_catches_unknown_parent(self):
        pts = [(0, 0), (40, 0), (40, 40), (0, 40)]
        part = Part(name="orphan", items=[bezier_path(pts), fill("#FFFFFF")],
                    pivot=(20, 20), pos=(256, 256), parent="ghost")
        problems = Rig(name="x", parts=[part]).audit()
        self.assertTrue(any("parent" in p for p in problems))

    def test_build_character_rejects_bad_rig(self):
        pts = [(0, 0), (40, 0), (40, 40), (0, 40)]
        part = Part(name="bad", items=[bezier_path(pts), fill("#FFFFFF")],
                    pivot=(900, 900), pos=(256, 256))
        with self.assertRaises(ValueError):
            build_character(Rig(name="x", parts=[part]))


class TestOptimize(unittest.TestCase):
    def test_roundtrip_through_tgs_file(self, tmp_path=None):
        import tempfile
        from pathlib import Path
        doc = build_character(make_rig())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.tgs"
            size = dump_tgs(doc, path)
            self.assertLess(size, 64 * 1024)
            loaded, loaded_size = load_tgs(path)
            self.assertEqual(loaded_size, size)
            report = validate_doc(loaded, loaded_size)
            self.assertTrue(report.ok, [f.detail for f in report.errors])

    def test_optimize_never_grows_and_stays_valid(self):
        import gzip
        import json
        doc = build_character(make_rig())
        before = len(gzip.compress(json.dumps(doc).encode(), compresslevel=9, mtime=0))
        optimized, stats = optimize_doc(doc)
        after = len(gzip.compress(json.dumps(optimized, separators=(",", ":")).encode(),
                                  compresslevel=9, mtime=0))
        self.assertLessEqual(after, before)
        self.assertTrue(validate_doc(optimized, after).ok)


if __name__ == "__main__":
    unittest.main()
