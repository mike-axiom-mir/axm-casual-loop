import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module


class DependencyGapTests(unittest.TestCase):
    def build_spec(self):
        return LoopSpec(
            loop_id="test.dependency-gap/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda s: not s["done"], "start"),
            end_invariant=Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            max_waves=4,
        )

    def test_dependency_metadata_currently_does_not_gate_execution(self):
        """Detection proof: declared dependency is currently signed metadata only."""

        prerequisite = Module(
            "prerequisite",
            "0.01",
            ("ready",),
            lambda _s: False,
            lambda _s: {"ready": True},
            authority_scope=("ready",),
        )
        dependent = Module(
            "dependent",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("prerequisite",),
        )
        receipt = CausalLoopEngine(self.build_spec(), [prerequisite, dependent]).run(
            {"ready": False, "done": False}
        )

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], ["dependent"])
        self.assertFalse(receipt["endState"]["ready"])
        self.assertTrue(receipt["endState"]["done"])

    def test_unknown_dependency_name_is_currently_accepted(self):
        """Detection proof: typo/missing dependency IDs are not validated yet."""

        dependent = Module(
            "dependent",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("does-not-exist",),
        )
        engine = CausalLoopEngine(self.build_spec(), [dependent])
        receipt = engine.run({"done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], ["dependent"])


if __name__ == "__main__":
    unittest.main()
