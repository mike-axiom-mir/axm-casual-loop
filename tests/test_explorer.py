import unittest

from causal_loop.explorer import bounded_schedule_cases, explore_schedule_space
from causal_loop.train_platform import build_engine, initial_state


ACTIONS = ("BLOCK_DOOR", "TRIGGER_ALARM", "TALK_TO_PASSENGER")
WAVES = range(6)


class CausalAtlasTests(unittest.TestCase):
    def build_atlas(self):
        cases = bounded_schedule_cases(ACTIONS, WAVES)
        return explore_schedule_space(build_engine(), initial_state(), cases)

    def test_bounded_space_has_expected_case_count(self):
        cases = bounded_schedule_cases(ACTIONS, WAVES)
        self.assertEqual(len(cases), 145)
        self.assertEqual(len({case.case_id for case in cases}), 145)

    def test_atlas_repeats_every_case_and_finds_no_hash_mismatch(self):
        atlas = self.build_atlas()
        self.assertEqual(atlas["summary"]["caseCount"], 145)
        self.assertEqual(atlas["summary"]["deterministicMismatchCount"], 0)
        self.assertEqual(atlas["deterministicMismatchCases"], [])
        self.assertTrue(all(case["deterministicRepeat"] for case in atlas["cases"]))

    def test_bounded_space_preserves_hard_invariants_without_contradictions(self):
        atlas = self.build_atlas()
        self.assertEqual(atlas["summary"]["hardInvariantFailureCaseCount"], 0)
        self.assertEqual(atlas["summary"]["contradictionCaseCount"], 0)
        self.assertEqual(atlas["summary"]["failedCount"], 0)
        self.assertEqual(atlas["summary"]["convergedCount"], 145)

    def test_atlas_exposes_current_orphan_talk_direction(self):
        atlas = self.build_atlas()
        self.assertIn("player.talkingToPassenger", atlas["summary"]["orphanExternalWriteKeys"])
        affected = [
            case
            for case in atlas["cases"]
            if "player.talkingToPassenger" in case["orphanExternalWriteKeys"]
        ]
        self.assertTrue(affected)
        self.assertTrue(any("TALK_TO_PASSENGER" in case["caseId"] for case in affected))

    def test_atlas_exposes_direction_that_can_survive_to_convergence(self):
        atlas = self.build_atlas()
        keys = atlas["summary"]["unresolvedExternalWriteKeys"]
        self.assertIn("player.talkingToPassenger", keys)
        self.assertIn("player.blockingDoor", keys)

    def test_same_atlas_input_produces_same_atlas_hash(self):
        cases = bounded_schedule_cases(ACTIONS, WAVES)
        a = explore_schedule_space(build_engine(), initial_state(), cases)
        b = explore_schedule_space(build_engine(), initial_state(), cases)
        self.assertEqual(a["atlasHash"], b["atlasHash"])
        self.assertEqual(a["summary"], b["summary"])


if __name__ == "__main__":
    unittest.main()
