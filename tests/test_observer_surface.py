from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.export_demo_receipt import build_demo_receipt


ROOT = Path(__file__).resolve().parents[1]


class ObserverSurfaceTests(unittest.TestCase):
    def test_bundled_demo_matches_current_engine_exactly(self) -> None:
        bundled = json.loads(
            (ROOT / "observer" / "demo-receipt.json").read_text(encoding="utf-8")
        )

        self.assertEqual(bundled, build_demo_receipt())

    def test_guided_causal_reading_controls_remain_present(self) -> None:
        surface = (ROOT / "observer" / "index.html").read_text(encoding="utf-8")

        for required_id in (
            'id="demo"',
            'id="timeline"',
            'id="eventType"',
            'id="changes"',
            'id="surfaceStatus"',
        ):
            self.assertIn(required_id, surface)
        self.assertIn("prefers-reduced-motion", surface)
        self.assertIn("autoplay:!reducedMotion", surface)
        self.assertIn("Observer only · non-authoritative", surface)


if __name__ == "__main__":
    unittest.main()
