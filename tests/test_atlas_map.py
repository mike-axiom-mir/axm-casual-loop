from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from causal_loop.explorer import bounded_schedule_cases, explore_schedule_space
from causal_loop.train_platform import build_engine, initial_state
from scripts.build_atlas_map import render_atlas_map


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_atlas_map.py"


def build_small_atlas() -> dict:
    engine = build_engine()
    cases = bounded_schedule_cases(
        ("BLOCK_DOOR", "TRIGGER_ALARM"),
        range(3),
        max_actions_per_case=1,
    )
    return explore_schedule_space(engine, initial_state(), cases)


class AtlasMapExperienceTests(unittest.TestCase):
    def test_real_verified_atlas_projects_truthfully(self) -> None:
        atlas = build_small_atlas()
        rendered = render_atlas_map(atlas)
        self.assertIn("Causal Atlas Map", rendered)
        self.assertIn(atlas["atlasHash"], rendered)
        self.assertIn("DISPLAY_ONLY_NO_EXECUTION_NO_SELECTION_NO_CANON", rendered)
        self.assertIn('"caseCount":7', rendered)
        self.assertIn("Compare nearest timing sibling", rendered)
        self.assertIn("Truth ceiling:", rendered)

    def test_render_is_deterministic(self) -> None:
        atlas = build_small_atlas()
        self.assertEqual(render_atlas_map(atlas), render_atlas_map(deepcopy(atlas)))

    def test_tampered_atlas_is_rejected_before_render(self) -> None:
        atlas = build_small_atlas()
        atlas["summary"]["caseCount"] += 1
        with self.assertRaisesRegex(ValueError, "atlasHash"):
            render_atlas_map(atlas)

    def test_cli_writes_one_self_contained_html_file(self) -> None:
        atlas = build_small_atlas()
        with tempfile.TemporaryDirectory() as temp:
            atlas_path = Path(temp) / "atlas.json"
            output = Path(temp) / "atlas-map.html"
            atlas_path.write_text(json.dumps(atlas), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(SCRIPT), str(atlas_path), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(output.is_file())
            body = output.read_text(encoding="utf-8")
            self.assertIn(atlas["atlasHash"], body)
            self.assertNotIn("http://", body)
            self.assertNotIn("https://", body)
            receipt = json.loads(run.stdout)
            self.assertEqual(receipt["atlasHash"], atlas["atlasHash"])
            self.assertEqual(receipt["authority"], "DISPLAY_ONLY_NO_EXECUTION_NO_SELECTION_NO_CANON")


if __name__ == "__main__":
    unittest.main()
