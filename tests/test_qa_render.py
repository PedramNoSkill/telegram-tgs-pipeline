import unittest

try:
    from PIL import Image  # noqa: F401
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

from tgspipe.build import build_character
from examples_build import make_rig


@unittest.skipUnless(HAS_PILLOW, "Pillow لازم است")
class TestRenderQa(unittest.TestCase):
    def test_render_and_qa_gates(self):
        from tgspipe.qa import qa_frames
        from tgspipe.render import render_frames

        doc = build_character(make_rig())
        frames = render_frames(doc, count=24, size=100)
        self.assertEqual(len(frames), 24)
        self.assertEqual(frames[0].size, (100, 100))
        report = qa_frames(frames)
        self.assertFalse(report.frozen)
        self.assertLess(report.seam, 2.0, "درز لوپ باید تقریباً صفر باشد")


if __name__ == "__main__":
    unittest.main()
