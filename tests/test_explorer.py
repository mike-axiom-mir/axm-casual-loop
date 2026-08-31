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
        self.assertEqual(len(cases), 208)
        self.assertEqual(len({case.case_id for case in cases}), 208)

    def test_repeated_action_cases_are_included(self):
        case_ids = {case.case_id for case in bounded_schedule_cases(ACTIONS, WAVES)}
        self.assertIn("pair-repeat:BLOCK_DOOR@0+BLOCK_DOOR@3", case_ids)
        self.assertIn("pair-repeat:TRIGGER_ALARM@1+TRIGGER_ALARM@4", case_ids)
        self.assertIn("pair-repeat:TALK_TO_PASSENGER@2+TALK_TO_PASSENGER@2", case_ids)

    def test_atlas_repeats_every_case_and_finds_no_hash_mismatch(self):
        atlas = self.build_atlas()
        self.assertEqual(atlas["summary"]["caseCount"], 208)
        self.assertEqual(atlas["summary"]["deterministicMismatchCount"], 0)
        self.assertEqual(atlas["deterministicMismatchCases"], [])
        self.assertTrue(all(case["deterministicRepeat"] for case in atlas["cases"]))

    def test_expanded_space_converges_without_detected_causal_debt(self):
        atlas = self.build_atlas()
        summary = atlas["summary"]
        self.assertEqual(summary["convergedCount"], 208)
        self.assertEqual(summary["failedCount"], 0)
        self.assertEqual(summary["failuresByReason"], {})
        self.assertEqual(summary["hardInvariantFailureCaseCount"], 0)
        self.assertEqual(summary["contradictionCaseCount"], 0)
        self.assertEqual(summary["authorityViolationCaseCount"], 0)
        self.assertEqual(summary["readViolationCaseCount"], 0)
        self.assertEqual(summary["orphanExternalWriteKeys"], [])
        self.assertEqual(summary["unresolvedExternalWriteKeys"], [])

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

    def test_two_separate_block_incidents_accumulate_two_delay_units(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[
                TimedInfluence(2, "BLOCK_DOOR"),
                TimedInfluence(4, "BLOCK_DOOR"),
            ],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["endState"]["delay.block"], 2)
        self.assertEqual(receipt["endState"]["train.departureDelay"], 2)
        self.assertEqual(receipt["modulesActivated"].count("04-obstruction"), 2)

    def test_two_separate_alarm_incidents_accumulate_four_delay_units(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[
                TimedInfluence(0, "TRIGGER_ALARM"),
                TimedInfluence(2, "TRIGGER_ALARM"),
            ],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["endState"]["delay.alarm"], 4)
        self.assertEqual(receipt["endState"]["train.departureDelay"], 4)
        self.assertEqual(receipt["modulesActivated"].count("05-alarm-trigger"), 2)

    def test_same_wave_duplicate_alarm_is_one_realized_incident(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[
                TimedInfluence(0, "TRIGGER_ALARM"),
                TimedInfluence(0, "TRIGGER_ALARM"),
            ],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["endState"]["delay.alarm"], 2)
        self.assertEqual(receipt["modulesActivated"].count("05-alarm-trigger"), 1)
        self.assertEqual(receipt["appliedTimedInfluences"][1]["writes"], {})

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
