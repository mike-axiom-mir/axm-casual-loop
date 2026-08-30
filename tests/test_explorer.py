import unittest

from causal_loop.engine import TimedInfluence
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

    def test_atlas_has_no_orphan_external_write_keys_after_repair(self):
        atlas = self.build_atlas()
        self.assertEqual(atlas["summary"]["orphanExternalWriteKeys"], [])

    def test_atlas_has_no_unresolved_external_write_keys_after_repair(self):
        atlas = self.build_atlas()
        self.assertEqual(atlas["summary"]["unresolvedExternalWriteKeys"], [])

    def test_talk_direction_is_consumed_by_a_deterministic_module(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[TimedInfluence(2, "TALK_TO_PASSENGER")],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertIn("13-passenger-conversation", receipt["modulesActivated"])
        self.assertTrue(receipt["endState"]["passenger.talkedTo"])
        self.assertFalse(receipt["endState"]["player.talkingToPassenger"])

    def test_late_block_is_a_noop_not_sticky_impossible_state(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[TimedInfluence(4, "BLOCK_DOOR")],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["appliedTimedInfluences"][0]["writes"], {})
        self.assertFalse(receipt["endState"]["player.blockingDoor"])
        self.assertEqual(receipt["endState"]["train.departureDelay"], 0)

    def test_departed_state_cannot_pass_hard_invariant_with_causal_debt(self):
        engine = build_engine()
        state = initial_state()
        state["train.status"] = "departed"
        state["player.triggerAlarm"] = True
        debt_guard = next(
            invariant
            for invariant in engine.spec.hard_invariants
            if invariant.invariant_id == "departure_has_no_causal_debt"
        )
        self.assertFalse(debt_guard.evaluate(state))

    def test_same_atlas_input_produces_same_atlas_hash(self):
        cases = bounded_schedule_cases(ACTIONS, WAVES)
        a = explore_schedule_space(build_engine(), initial_state(), cases)
        b = explore_schedule_space(build_engine(), initial_state(), cases)
        self.assertEqual(a["atlasHash"], b["atlasHash"])
        self.assertEqual(a["summary"], b["summary"])


if __name__ == "__main__":
    unittest.main()
