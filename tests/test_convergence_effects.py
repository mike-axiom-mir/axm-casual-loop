import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module


class ConvergenceEffectGapTests(unittest.TestCase):
    def build_spec(self):
        return LoopSpec(
            loop_id="test.convergence-effect-gap/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda s: not s["done"], "start"),
            end_invariant=Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            max_waves=4,
        )

    def test_hard_endpoint_can_converge_without_any_declared_convergence_effect(self):
        finisher = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=(),
        )
        receipt = CausalLoopEngine(self.build_spec(), [finisher]).run({"done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], ["finisher"])
        self.assertTrue(receipt["endState"]["done"])

    def test_declared_convergence_effect_does_not_make_a_non_endpoint_state_converge(self):
        marker = Module(
            "marker",
            "0.01",
            ("touched",),
            lambda s: not s["touched"],
            lambda _s: {"touched": True},
            authority_scope=("touched",),
            convergence_effects=("world_finished",),
        )
        receipt = CausalLoopEngine(self.build_spec(), [marker]).run(
            {"done": False, "touched": False}
        )

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "no_relevant_module")
        self.assertEqual(receipt["modulesActivated"], ["marker"])
        self.assertFalse(receipt["endState"]["done"])

    def test_declared_effect_changes_contract_signature_but_not_causal_path(self):
        plain = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=(),
        )
        decorated = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=("world_finished",),
        )
        plain_engine = CausalLoopEngine(self.build_spec(), [plain])
        decorated_engine = CausalLoopEngine(self.build_spec(), [decorated])
        plain_receipt = plain_engine.run({"done": False})
        decorated_receipt = decorated_engine.run({"done": False})

        self.assertNotEqual(plain_engine.engine_signature, decorated_engine.engine_signature)
        self.assertEqual(plain_receipt["modulesActivated"], decorated_receipt["modulesActivated"])
        self.assertEqual(plain_receipt["stateTransitions"], decorated_receipt["stateTransitions"])
        self.assertEqual(plain_receipt["endStateHash"], decorated_receipt["endStateHash"])
        self.assertNotIn("realizedConvergenceEffects", decorated_receipt)


if __name__ == "__main__":
    unittest.main()
