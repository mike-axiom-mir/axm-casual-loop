import unittest

from causal_loop.engine import (
    CausalLoopEngine,
    Invariant,
    LoopSpec,
    Module,
    TimedInfluence,
    commit_receipt_to_history,
)
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
            "oscillator", "0.01", ("bit",), lambda _s: True,
            lambda s: {"bit": 0 if s["bit"] else 1}, authority_scope=("bit",),
        )
        spec = LoopSpec(
            loop_id="test.oscillator/v0.01",
            version="0.02",
            start_invariant=Invariant("start", lambda s: s["bit"] in {0, 1}, "start"),
            end_invariant=Invariant("never", lambda _s: False, "hard_end"),
            hard_invariants=(), soft_invariants=(),
            intervention_handler=lambda _action, _state: {}, max_waves=10,
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
        self.assertEqual(initial_state()["train.status"], "approaching")
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

    def test_same_timed_intervention_sequence_replays_exactly(self):
        engine = build_engine()
        schedule = [TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(3, "TRIGGER_ALARM")]
        first = engine.run(initial_state(), timed_influences=schedule)
        second = engine.run(initial_state(), timed_influences=schedule)
        replay = engine.replay(first)
        self.assertEqual(first["status"], "converged")
        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(first["stateTransitions"], second["stateTransitions"])
        self.assertTrue(replay["replayMatches"])

    def test_same_action_at_different_causal_moment_changes_valid_result(self):
        engine = build_engine()
        while_open = engine.run(initial_state(), timed_influences=[TimedInfluence(2, "BLOCK_DOOR")])
        after_close = engine.run(initial_state(), timed_influences=[TimedInfluence(4, "BLOCK_DOOR")])
        self.assertEqual(while_open["status"], "converged")
        self.assertEqual(after_close["status"], "converged")
        self.assertEqual(while_open["endState"]["train.departureDelay"], 1)
        self.assertEqual(after_close["endState"]["train.departureDelay"], 0)
        self.assertNotEqual(while_open["endStateHash"], after_close["endStateHash"])

    def test_timed_action_cannot_rewrite_past_closed_door(self):
        receipt = build_engine().run(initial_state(), timed_influences=[TimedInfluence(4, "BLOCK_DOOR")])
        self.assertEqual(receipt["status"], "converged")
        self.assertNotIn("04-obstruction", receipt["modulesActivated"])
        self.assertEqual(receipt["endState"]["delay.block"], 0)
        self.assertEqual(receipt["endState"]["train.departureDelay"], 0)
        self.assertEqual(receipt["appliedTimedInfluences"][0]["atWave"], 4)
        self.assertEqual(receipt["appliedTimedInfluences"][0]["action"], "BLOCK_DOOR")
        self.assertEqual(receipt["appliedTimedInfluences"][0]["writes"], {})
        self.assertFalse(any(t["kind"] == "external" for t in receipt["stateTransitions"]))
        self.assertFalse(receipt["endState"]["player.blockingDoor"])

    def test_future_intervention_is_visible_if_loop_converges_before_it(self):
        receipt = build_engine().run(initial_state(), timed_influences=[TimedInfluence(9, "TRIGGER_ALARM")])
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["appliedTimedInfluences"], [])
        self.assertEqual(receipt["unappliedTimedInfluences"][0]["atWave"], 9)
        self.assertEqual(receipt["endState"]["train.departureDelay"], 0)

    def test_timed_input_order_at_same_wave_is_part_of_receipt(self):
        receipt = build_engine().run(
            initial_state(),
            timed_influences=[TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(2, "TRIGGER_ALARM")],
        )
        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(
            [(i["atWave"], i["sequence"], i["action"]) for i in receipt["timedExternalInfluences"]],
            [(2, 0, "BLOCK_DOOR"), (2, 1, "TRIGGER_ALARM")],
        )
        self.assertEqual(receipt["endState"]["train.departureDelay"], 3)

    def test_legacy_and_timed_inputs_cannot_be_mixed_ambiguously(self):
        with self.assertRaises(ValueError):
            build_engine().run(
                initial_state(), ["BLOCK_DOOR"], timed_influences=[TimedInfluence(2, "TRIGGER_ALARM")]
            )

    def test_checkpoint_resume_matches_uninterrupted_run_exactly(self):
        engine = build_engine()
        schedule = [TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(3, "TRIGGER_ALARM")]
        uninterrupted = engine.run(initial_state(), timed_influences=schedule)
        checkpoint = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)
        resumed = engine.resume(checkpoint)
        self.assertEqual(uninterrupted["status"], "converged")
        self.assertEqual(resumed["receiptHash"], uninterrupted["receiptHash"])
        self.assertEqual(resumed["stateTransitions"], uninterrupted["stateTransitions"])
        self.assertEqual(resumed["convergencePath"], uninterrupted["convergencePath"])
        self.assertEqual(resumed["endStateHash"], uninterrupted["endStateHash"])

    def test_checkpoint_boundary_does_not_consume_future_timed_action_early(self):
        engine = build_engine()
        schedule = [TimedInfluence(2, "BLOCK_DOOR")]
        checkpoint = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)
        self.assertEqual(checkpoint["wavesExecuted"], 2)
        self.assertEqual(checkpoint["appliedTimedInfluences"], [])
        resumed = engine.resume(checkpoint)
        self.assertEqual(resumed["endState"]["train.departureDelay"], 1)
        self.assertEqual(len(resumed["appliedTimedInfluences"]), 1)
        self.assertEqual(resumed["appliedTimedInfluences"][0]["atWave"], 2)

    def test_same_pause_point_produces_same_checkpoint_hash(self):
        engine = build_engine()
        schedule = [TimedInfluence(2, "BLOCK_DOOR")]
        a = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)
        b = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)
        self.assertEqual(a["checkpointHash"], b["checkpointHash"])
        self.assertEqual(a["stateHash"], b["stateHash"])

    def test_tampered_checkpoint_is_rejected(self):
        engine = build_engine()
        checkpoint = engine.pause(initial_state(), timed_influences=[TimedInfluence(2, "BLOCK_DOOR")], after_waves=2)
        checkpoint["state"]["door.state"] = "teleported_open_elsewhere"
        with self.assertRaises(ValueError):
            engine.resume(checkpoint)

    def test_resumed_committed_run_enters_history_once(self):
        engine = build_engine()
        checkpoint = engine.pause(initial_state(), timed_influences=[TimedInfluence(2, "BLOCK_DOOR")], after_waves=2)
        resumed = engine.resume(checkpoint, commit=True)
        history = []
        commit_receipt_to_history(resumed, history)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["runId"], resumed["runId"])


if __name__ == "__main__":
    unittest.main()