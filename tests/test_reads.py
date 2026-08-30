import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module
from causal_loop.train_platform import build_engine, initial_state


class ReadScopeTests(unittest.TestCase):
    def build_spec(self, end_predicate=lambda _s: False):
        return LoopSpec(
            loop_id="test.read-scope/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda _s: True, "start"),
            end_invariant=Invariant("end", end_predicate, "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            max_waves=4,
        )

    def test_undeclared_predicate_read_fails_without_state_change(self):
        sneaky = Module(
            "sneaky-predicate",
            "0.01",
            ("declared",),
            lambda s: s["secret"] == 7,
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        engine = CausalLoopEngine(self.build_spec(), [sneaky])
        start = {"declared": True, "secret": 7, "done": False}
        receipt = engine.run(start)

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "read_scope_violation")
        self.assertEqual(receipt["endState"], start)
        self.assertEqual(receipt["stateTransitions"], [])
        violation = receipt["readViolations"][0]
        self.assertEqual(violation["moduleId"], "sneaky-predicate")
        self.assertEqual(violation["phase"], "predicate")
        self.assertEqual(violation["undeclaredKey"], "secret")
        self.assertEqual(violation["declaredReads"], ["declared"])

    def test_undeclared_transition_read_fails_before_authorized_write_commits(self):
        sneaky = Module(
            "sneaky-transition",
            "0.01",
            ("trigger",),
            lambda s: s["trigger"],
            lambda s: {"done": bool(s["secret"])},
            authority_scope=("done",),
        )
        engine = CausalLoopEngine(self.build_spec(), [sneaky])
        start = {"trigger": True, "secret": 1, "done": False}
        receipt = engine.run(start)

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "read_scope_violation")
        self.assertEqual(receipt["endState"], start)
        self.assertEqual(receipt["modulesActivated"], [])
        self.assertEqual(receipt["stateTransitions"], [])
        violation = receipt["readViolations"][0]
        self.assertEqual(violation["moduleId"], "sneaky-transition")
        self.assertEqual(violation["phase"], "transition")
        self.assertEqual(violation["undeclaredKey"], "secret")

    def test_declared_read_can_drive_authorized_write(self):
        lawful = Module(
            "lawful",
            "0.01",
            ("source", "done"),
            lambda s: not s["done"],
            lambda s: {"done": bool(s["source"])},
            authority_scope=("done",),
        )
        engine = CausalLoopEngine(self.build_spec(lambda s: s["done"]), [lawful])
        receipt = engine.run({"source": 1, "done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertTrue(receipt["endState"]["done"])
        self.assertEqual(receipt["readViolations"], [])
        self.assertEqual(receipt["resourceUsage"]["readViolationCount"], 0)

    def test_read_violation_receipt_is_deterministic(self):
        sneaky = Module(
            "sneaky",
            "0.01",
            ("trigger",),
            lambda s: s["trigger"] and s["secret"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        engine = CausalLoopEngine(self.build_spec(), [sneaky])
        start = {"trigger": True, "secret": True, "done": False}
        first = engine.run(start)
        second = engine.run(start)

        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(first["readViolations"], second["readViolations"])
        self.assertEqual(first["endStateHash"], second["endStateHash"])

    def test_train_detection_identifies_guard_hidden_trigger_read(self):
        receipt = build_engine().run(initial_state(), ["BLOCK_DOOR"])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "read_scope_violation")
        self.assertTrue(
            any(
                item["moduleId"] == "09-guard-investigate"
                and item["phase"] == "transition"
                and item["undeclaredKey"] == "player.triggerAlarm"
                for item in receipt["readViolations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
