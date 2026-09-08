import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module


class AuthorityScopeTests(unittest.TestCase):
    def build_spec(self, end_predicate=lambda _s: False):
        return LoopSpec(
            loop_id="test.authority/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda _s: True, "start"),
            end_invariant=Invariant("end", end_predicate, "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            max_waves=4,
        )

    def test_out_of_scope_write_fails_before_any_wave_write_is_committed(self):
        rogue = Module(
            "rogue",
            "0.01",
            ("trigger",),
            lambda s: s["trigger"],
            lambda _s: {"owned": 1, "foreign": 9},
            authority_scope=("owned",),
        )
        engine = CausalLoopEngine(self.build_spec(), [rogue])
        start = {"trigger": True, "owned": 0, "foreign": 0}
        receipt = engine.run(start)

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "authority_scope_violation")
        self.assertEqual(receipt["endState"], start)
        self.assertEqual(receipt["stateTransitions"], [])
        self.assertEqual(receipt["modulesActivated"], [])
        self.assertEqual(receipt["resourceUsage"]["authorityViolationCount"], 1)

        violation = receipt["authorityViolations"][0]
        self.assertEqual(violation["wave"], 0)
        self.assertEqual(violation["moduleId"], "rogue")
        self.assertEqual(violation["unauthorizedKeys"], ["foreign"])
        self.assertEqual(violation["proposedWrites"], {"foreign": 9})

    def test_authorized_write_can_enter_canonical_state(self):
        lawful = Module(
            "lawful",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        engine = CausalLoopEngine(self.build_spec(lambda s: s["done"]), [lawful])
        receipt = engine.run({"done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertTrue(receipt["endState"]["done"])
        self.assertEqual(receipt["authorityViolations"], [])
        self.assertEqual(receipt["resourceUsage"]["authorityViolationCount"], 0)

    def test_authority_violation_receipt_is_deterministic(self):
        rogue = Module(
            "rogue",
            "0.01",
            ("trigger",),
            lambda s: s["trigger"],
            lambda _s: {"foreign": 9},
            authority_scope=(),
        )
        engine = CausalLoopEngine(self.build_spec(), [rogue])
        start = {"trigger": True, "foreign": 0}
        first = engine.run(start)
        second = engine.run(start)

        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(first["authorityViolations"], second["authorityViolations"])
        self.assertEqual(first["endStateHash"], second["endStateHash"])


if __name__ == "__main__":
    unittest.main()
