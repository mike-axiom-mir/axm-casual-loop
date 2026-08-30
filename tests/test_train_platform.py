import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module, commit_receipt_to_history
from causal_loop.train_platform import build_engine, initial_state, intervention_handler


class TrainPlatformProofTests(unittest.TestCase):
    def test_same_start_and_same_ordered_inputs_same_end_hash_and_trace(self):
        engine = build_engine()
        a = engine.run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        b = engine.run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        self.assertEqual(a["status"], "converged")
        self.assertEqual(a["endStateHash"], b["endStateHash"])
        self.assertEqual(a["modulesActivated"], b["modulesActivated"])
        self.assertEqual(a["stateTransitions"], b["stateTransitions"])
        self.assertEqual(a["receiptHash"], b["receiptHash"])

    def test_different_external_influence_changes_valid_causal_path(self):
        engine = build_engine()
        normal = engine.run(initial_state(), ["WAIT"])
        blocked = engine.run(initial_state(), ["BLOCK_DOOR"])
        self.assertEqual(normal["status"], "converged")
        self.assertEqual(blocked["status"], "converged")
        self.assertNotEqual(normal["modulesActivated"], blocked["modulesActivated"])
        self.assertEqual(normal["endState"]["train.status"], "departed")
        self.assertEqual(blocked["endState"]["train.status"], "departed")

    def test_block_and_alarm_both_propagate_when_both_are_requested(self):
        receipt = build_engine().run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        self.assertEqual(receipt["status"], "converged")
        self.assertIn("04-obstruction", receipt["modulesActivated"])
        self.assertIn("05-alarm-trigger", receipt["modulesActivated"])
        self.assertEqual(receipt["endState"]["delay.block"], 1)
        self.assertEqual(receipt["endState"]["delay.alarm"], 2)
        self.assertEqual(receipt["endState"]["train.departureDelay"], 3)

    def test_hard_invariants_hold_on_success(self):
        receipt = build_engine().run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        hard_results = [r for r in receipt["invariantResults"] if r["kind"] in {"hard", "hard_end"}]
        self.assertTrue(hard_results)
        self.assertTrue(all(r["passed"] for r in hard_results))

    def test_soft_invariant_can_be_displaced(self):
        receipt = build_engine().run(initial_state(), ["BLOCK_DOOR"])
        soft = next(r for r in receipt["invariantResults"] if r["id"] == "on_time_departure")
        self.assertEqual(receipt["status"], "converged")
        self.assertFalse(soft["passed"])
        self.assertGreater(receipt["endState"]["train.departureDelay"], 0)

    def test_irrelevant_modules_do_not_execute(self):
        receipt = build_engine().run(initial_state(), ["WAIT"])
        self.assertNotIn("09-guard-investigate", receipt["modulesActivated"])
        self.assertNotIn("99-unused-snow-module", receipt["modulesActivated"])

    def test_registry_order_does_not_change_canonical_result(self):
        normal = build_engine(reverse_registry=False).run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        reversed_registry = build_engine(reverse_registry=True).run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
        self.assertEqual(normal["endStateHash"], reversed_registry["endStateHash"])
        self.assertEqual(normal["modulesActivated"], reversed_registry["modulesActivated"])
        self.assertEqual(normal["stateTransitions"], reversed_registry["stateTransitions"])

    def test_causal_cycle_is_detected_and_bounded(self):
        oscillator = Module(
            "oscillator",
            "0.01",
            ("bit",),
            lambda _s: True,
            lambda s: {"bit": 0 if s["bit"] else 1},
            authority_scope=("bit",),
        )
        spec = LoopSpec(
            loop_id="test.oscillator/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda s: s["bit"] in {0, 1}, "start"),
            end_invariant=Invariant("never", lambda _s: False, "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            max_waves=10,
        )
        receipt = CausalLoopEngine(spec, [oscillator]).run({"bit": 0})
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "causal_cycle_detected")
        self.assertLess(receipt["resourceUsage"]["causalDepth"], 10)

    def test_convergence_failure_has_explicit_receipt(self):
        receipt = build_engine().run(initial_state(), ["WAIT"], max_waves=1)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "event_budget_exhausted")
        self.assertFalse(next(r for r in receipt["invariantResults"] if r["kind"] == "hard_end")["passed"])

    def test_replay_reconstructs_exact_run(self):
        engine = build_engine()
        receipt = engine.run(initial_state(), ["TRIGGER_ALARM"], commit=True)
        replay = engine.replay(receipt)
        self.assertTrue(replay["replayMatches"])
        self.assertEqual(receipt["endStateHash"], replay["endStateHash"])
        self.assertEqual(receipt["stateTransitions"], replay["stateTransitions"])

    def test_history_persists_separately_from_operational_state(self):
        engine = build_engine()
        history = []
        committed = engine.run(initial_state(), ["BLOCK_DOOR"], commit=True)
        commit_receipt_to_history(committed, history)
        self.assertEqual(len(history), 1)
        reset_state = initial_state()
        self.assertEqual(reset_state["train.status"], "approaching")
        self.assertEqual(history[0]["runId"], committed["runId"])

    def test_uncommitted_event_cannot_enter_history(self):
        history = []
        uncommitted = build_engine().run(initial_state(), ["WAIT"], commit=False)
        with self.assertRaises(ValueError):
            commit_receipt_to_history(uncommitted, history)
        self.assertEqual(history, [])

    def test_loop_runs_headless_without_rendering(self):
        receipt = build_engine().run(initial_state(), ["WAIT"])
        self.assertTrue(receipt["headless"])
        self.assertEqual(receipt["status"], "converged")

    def test_external_action_sets_direction_not_authoritative_consequence(self):
        writes = intervention_handler("BLOCK_DOOR", initial_state())
        self.assertEqual(writes, {"player.blockingDoor": True})
        self.assertNotIn("train.departureDelay", writes)
        receipt = build_engine().run(initial_state(), ["BLOCK_DOOR"])
        self.assertGreater(receipt["endState"]["train.departureDelay"], 0)


if __name__ == "__main__":
    unittest.main()
