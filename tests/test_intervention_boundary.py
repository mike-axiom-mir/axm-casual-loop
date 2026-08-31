import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module
from causal_loop.train_platform import (
    INTERVENTION_WRITE_SCOPE,
    build_engine,
    intervention_handler,
    initial_state,
)


DIRECTION_KEYS = set(INTERVENTION_WRITE_SCOPE)


class InterventionBoundaryTests(unittest.TestCase):
    def test_train_intervention_handler_writes_only_direction_keys(self):
        state = initial_state()
        for action in ("WAIT", "BLOCK_DOOR", "TRIGGER_ALARM", "TALK_TO_PASSENGER"):
            writes = dict(intervention_handler(action, state))
            self.assertTrue(set(writes).issubset(DIRECTION_KEYS), (action, writes))
            self.assertNotIn("train.status", writes)
            self.assertNotIn("train.departureDelay", writes)
            self.assertNotIn("door.state", writes)
            self.assertNotIn("passenger.state", writes)

    def test_train_engine_declares_same_direction_scope_as_handler(self):
        engine = build_engine()
        self.assertEqual(set(engine.spec.intervention_write_scope), DIRECTION_KEYS)
        self.assertEqual(engine.spec.version, "0.08")

    def test_train_direction_handler_cannot_declare_delay_consequence(self):
        writes = dict(intervention_handler("BLOCK_DOOR", initial_state()))
        self.assertEqual(writes, {"player.blockingDoor": True})
        self.assertNotIn("delay.block", writes)
        self.assertNotIn("train.departureDelay", writes)

    def test_generic_engine_rejects_authoritative_intervention_write_before_state_change(self):
        consequence_key = "world.finished"
        spec = LoopSpec(
            loop_id="test.intervention-authority/v0.02",
            version="0.02",
            start_invariant=Invariant("start", lambda s: not s[consequence_key], "start"),
            end_invariant=Invariant("end", lambda s: s[consequence_key], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda action, _state: (
                {consequence_key: True} if action == "FINISH_WORLD" else {}
            ),
            max_waves=2,
            intervention_write_scope=("direction.requested",),
        )
        never_needed = Module(
            "never-needed",
            "0.01",
            (consequence_key,),
            lambda _s: False,
            lambda _s: {},
            authority_scope=(),
        )
        start = {consequence_key: False, "direction.requested": False}
        receipt = CausalLoopEngine(spec, [never_needed]).run(start, ["FINISH_WORLD"])

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "intervention_scope_violation")
        self.assertEqual(receipt["endState"], start)
        self.assertEqual(receipt["modulesActivated"], [])
        self.assertEqual(receipt["stateTransitions"], [])
        self.assertEqual(receipt["appliedTimedInfluences"], [])
        self.assertEqual(receipt["unappliedTimedInfluences"][0]["action"], "FINISH_WORLD")
        violation = receipt["interventionAuthorityViolations"][0]
        self.assertEqual(violation["unauthorizedKeys"], [consequence_key])
        self.assertEqual(violation["allowedWriteKeys"], ["direction.requested"])
        self.assertEqual(violation["proposedWrites"], {consequence_key: True})
        self.assertEqual(receipt["resourceUsage"]["interventionAuthorityViolationCount"], 1)

    def test_intervention_scope_violation_receipt_replays_deterministically(self):
        spec = LoopSpec(
            loop_id="test.intervention-authority-repeat/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda _s: True, "start"),
            end_invariant=Invariant("end", lambda s: s["world.finished"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {"world.finished": True},
            max_waves=2,
            intervention_write_scope=("direction.requested",),
        )
        idle = Module(
            "idle",
            "0.01",
            ("world.finished",),
            lambda _s: False,
            lambda _s: {},
            authority_scope=(),
        )
        engine = CausalLoopEngine(spec, [idle])
        start = {"world.finished": False, "direction.requested": False}
        first = engine.run(start, ["FINISH_WORLD"])
        second = engine.run(start, ["FINISH_WORLD"])
        replay = engine.replay(first)

        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(
            first["interventionAuthorityViolations"],
            second["interventionAuthorityViolations"],
        )
        self.assertTrue(replay["replayMatches"])

    def test_allowed_direction_still_requires_module_to_derive_consequence(self):
        spec = LoopSpec(
            loop_id="test.direction-to-consequence/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda s: not s["world.finished"], "start"),
            end_invariant=Invariant("end", lambda s: s["world.finished"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda action, _state: (
                {"direction.requested": True} if action == "REQUEST_FINISH" else {}
            ),
            max_waves=4,
            intervention_write_scope=("direction.requested",),
        )
        derive = Module(
            "derive-finish",
            "0.01",
            ("direction.requested", "world.finished"),
            lambda s: s["direction.requested"] and not s["world.finished"],
            lambda _s: {"world.finished": True},
            authority_scope=("world.finished",),
        )
        receipt = CausalLoopEngine(spec, [derive]).run(
            {"world.finished": False, "direction.requested": False},
            ["REQUEST_FINISH"],
        )

        self.assertEqual(receipt["status"], "converged")
        self.assertIn("derive-finish", receipt["modulesActivated"])
        self.assertEqual(receipt["interventionAuthorityViolations"], [])
        self.assertTrue(receipt["endState"]["world.finished"])


if __name__ == "__main__":
    unittest.main()
