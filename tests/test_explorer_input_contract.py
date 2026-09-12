import unittest

from causal_loop.engine import TimedInfluence
from causal_loop.explorer import ExplorationCase, bounded_schedule_cases, explore_schedule_space
from causal_loop.train_platform import build_engine, initial_state


class CausalAtlasInputContractTests(unittest.TestCase):
    def test_wave_validation_happens_before_deduplication(self):
        malformed = (
            [1, True],
            [True, 1],
            [1, 1.0],
            [1.0, 1],
        )
        for waves in malformed:
            with self.subTest(waves=waves):
                with self.assertRaisesRegex(ValueError, "non-negative integers"):
                    bounded_schedule_cases(("WAIT",), waves)

    def test_valid_duplicate_waves_still_deduplicate_deterministically(self):
        cases = bounded_schedule_cases(
            ("WAIT",),
            [2, 1, 2, 1],
            max_actions_per_case=1,
            include_empty=False,
        )
        self.assertEqual(
            [case.case_id for case in cases],
            ["single:WAIT@1", "single:WAIT@2"],
        )

    def test_action_input_is_explicitly_string_typed(self):
        for actions in ("WAIT", ("WAIT", ""), ("WAIT", True)):
            with self.subTest(actions=actions):
                with self.assertRaisesRegex(ValueError, "actions"):
                    bounded_schedule_cases(actions, (0,))

    def test_action_limit_rejects_bool_and_integral_float(self):
        for value in (True, 1.0, 2.0):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_actions_per_case"):
                    bounded_schedule_cases(("WAIT",), (0,), max_actions_per_case=value)

    def test_atlas_rejects_duplicate_case_identity_before_execution(self):
        duplicate_cases = (
            ExplorationCase("same", (TimedInfluence(0, "TRIGGER_ALARM"),)),
            ExplorationCase("same", (TimedInfluence(2, "TRIGGER_ALARM"),)),
        )
        with self.assertRaisesRegex(ValueError, "case_id values must be unique"):
            explore_schedule_space(build_engine(), initial_state(), duplicate_cases)

    def test_atlas_rejects_empty_case_identity(self):
        cases = (ExplorationCase("", ()),)
        with self.assertRaisesRegex(ValueError, "case_id values must be non-empty strings"):
            explore_schedule_space(build_engine(), initial_state(), cases)

    def test_repeat_count_is_exact_integer_contract(self):
        cases = (ExplorationCase("empty", ()),)
        for repeats in (True, 2.0, 1):
            with self.subTest(repeats=repeats):
                with self.assertRaisesRegex(ValueError, "repeats must be an integer >= 2"):
                    explore_schedule_space(
                        build_engine(),
                        initial_state(),
                        cases,
                        repeats=repeats,
                    )


if __name__ == "__main__":
    unittest.main()
