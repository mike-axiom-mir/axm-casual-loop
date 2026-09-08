import unittest

from causal_loop import engine_v06
from causal_loop.engine import (
    DEPENDENCY_POLICY,
    CausalLoopEngine,
    Invariant,
    LoopSpec,
    Module,
)


class DependencyContractTests(unittest.TestCase):
    def build_spec(self, *, loop_id="test.dependencies/v0.01", max_waves=6):
        return LoopSpec(
            loop_id=loop_id,
            version="0.01",
            start_invariant=Invariant("start", lambda s: not s["done"], "start"),
            end_invariant=Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            max_waves=max_waves,
        )

    def test_preserved_v06_baseline_proves_dependency_was_metadata_only(self):
        spec = engine_v06.LoopSpec(
            loop_id="test.dependency-baseline/v0.01",
            version="0.01",
            start_invariant=engine_v06.Invariant("start", lambda s: not s["done"], "start"),
            end_invariant=engine_v06.Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            max_waves=4,
        )
        prerequisite = engine_v06.Module(
            "prerequisite",
            "0.01",
            ("ready",),
            lambda _s: False,
            lambda _s: {"ready": True},
            authority_scope=("ready",),
        )
        dependent = engine_v06.Module(
            "dependent",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("prerequisite",),
        )
        receipt = engine_v06.CausalLoopEngine(spec, [prerequisite, dependent]).run(
            {"ready": False, "done": False}
        )

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], ["dependent"])
        self.assertFalse(receipt["endState"]["ready"])

    def test_dependency_waits_for_prior_committed_activation(self):
        prerequisite = Module(
            "prerequisite",
            "0.01",
            ("ready",),
            lambda s: not s["ready"],
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
        receipt = CausalLoopEngine(self.build_spec(), [dependent, prerequisite]).run(
            {"ready": False, "done": False}
        )

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], ["prerequisite", "dependent"])
        self.assertEqual(receipt["dependencyPolicy"], DEPENDENCY_POLICY)
        self.assertEqual(receipt["dependencyBlocks"][0]["wave"], 0)
        self.assertEqual(receipt["dependencyBlocks"][0]["moduleId"], "dependent")
        self.assertEqual(
            receipt["dependencyBlocks"][0]["missingDependencies"],
            ["prerequisite"],
        )
        prerequisite_transition = next(
            transition
            for transition in receipt["stateTransitions"]
            if transition.get("source") == "prerequisite"
        )
        dependent_transition = next(
            transition
            for transition in receipt["stateTransitions"]
            if transition.get("source") == "dependent"
        )
        self.assertLess(prerequisite_transition["wave"], dependent_transition["wave"])

    def test_unknown_dependency_id_is_rejected_at_engine_construction(self):
        dependent = Module(
            "dependent",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("does-not-exist",),
        )
        with self.assertRaisesRegex(ValueError, "unknown module"):
            CausalLoopEngine(self.build_spec(), [dependent])

    def test_self_dependency_is_rejected(self):
        self_dependent = Module(
            "self",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("self",),
        )
        with self.assertRaisesRegex(ValueError, "cannot depend on itself"):
            CausalLoopEngine(self.build_spec(), [self_dependent])

    def test_dependency_cycle_is_rejected(self):
        first = Module(
            "first",
            "0.01",
            ("done",),
            lambda _s: False,
            lambda _s: {},
            dependencies=("second",),
        )
        second = Module(
            "second",
            "0.01",
            ("done",),
            lambda _s: False,
            lambda _s: {},
            dependencies=("first",),
        )
        with self.assertRaisesRegex(ValueError, "dependency cycle detected"):
            CausalLoopEngine(self.build_spec(), [first, second])

    def test_duplicate_dependency_is_rejected(self):
        prerequisite = Module(
            "prerequisite",
            "0.01",
            ("ready",),
            lambda _s: False,
            lambda _s: {},
        )
        dependent = Module(
            "dependent",
            "0.01",
            ("done",),
            lambda _s: False,
            lambda _s: {},
            dependencies=("prerequisite", "prerequisite"),
        )
        with self.assertRaisesRegex(ValueError, "duplicate dependencies"):
            CausalLoopEngine(self.build_spec(), [prerequisite, dependent])

    def test_relevant_but_unreachable_dependency_fails_explicitly(self):
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
        start = {"ready": False, "done": False}
        engine = CausalLoopEngine(self.build_spec(), [prerequisite, dependent])
        receipt = engine.run(start)

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "unsatisfied_dependencies")
        self.assertEqual(receipt["endState"], start)
        self.assertEqual(receipt["modulesActivated"], [])
        self.assertEqual(receipt["resourceUsage"]["dependencyBlockCount"], 1)
        self.assertEqual(receipt["dependencyBlocks"][0]["missingDependencies"], ["prerequisite"])

    def test_unsatisfied_dependency_receipt_replays_exactly(self):
        prerequisite = Module(
            "prerequisite",
            "0.01",
            ("ready",),
            lambda _s: False,
            lambda _s: {},
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
        engine = CausalLoopEngine(self.build_spec(), [prerequisite, dependent])
        start = {"ready": False, "done": False}
        first = engine.run(start)
        second = engine.run(start)
        replay = engine.replay(first)

        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(first["dependencyBlocks"], second["dependencyBlocks"])
        self.assertTrue(replay["replayMatches"])

    def test_registry_order_cannot_satisfy_same_wave_dependency(self):
        prerequisite = Module(
            "z-prerequisite",
            "0.01",
            ("ready",),
            lambda s: not s["ready"],
            lambda _s: {"ready": True},
            authority_scope=("ready",),
        )
        dependent = Module(
            "a-dependent",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("z-prerequisite",),
        )
        start = {"ready": False, "done": False}
        forward = CausalLoopEngine(self.build_spec(), [dependent, prerequisite]).run(start)
        reverse = CausalLoopEngine(self.build_spec(), [prerequisite, dependent]).run(start)

        self.assertEqual(forward["receiptHash"], reverse["receiptHash"])
        self.assertEqual(forward["modulesActivated"], ["z-prerequisite", "a-dependent"])
        self.assertEqual(forward["modulesActivated"], reverse["modulesActivated"])


if __name__ == "__main__":
    unittest.main()
