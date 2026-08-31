import unittest

from causal_loop import engine_v07
from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module
from causal_loop.train_platform import build_engine, initial_state


class ConvergenceEffectContractTests(unittest.TestCase):
    def build_spec(self, *, required=()):
        return LoopSpec(
            loop_id="test.convergence-effect/v0.02",
            version="0.02",
            start_invariant=Invariant("start", lambda _s: True, "start"),
            end_invariant=Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            required_convergence_effects=tuple(required),
            max_waves=6,
        )

    def test_preserved_v07_baseline_proves_effects_were_metadata_only(self):
        spec = engine_v07.LoopSpec(
            loop_id="test.convergence-effect-baseline/v0.01",
            version="0.01",
            start_invariant=engine_v07.Invariant("start", lambda _s: True, "start"),
            end_invariant=engine_v07.Invariant("end", lambda s: s["done"], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda _action, _state: {},
            intervention_write_scope=(),
            max_waves=4,
        )
        marker = engine_v07.Module(
            "marker",
            "0.01",
            ("touched",),
            lambda s: not s["touched"],
            lambda _s: {"touched": True},
            authority_scope=("touched",),
            convergence_effects=("world_finished",),
        )
        receipt = engine_v07.CausalLoopEngine(spec, [marker]).run(
            {"done": False, "touched": False}
        )

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "no_relevant_module")
        self.assertNotIn("realizedConvergenceEffects", receipt)

    def test_effects_are_optional_when_loop_requires_none(self):
        finisher = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        receipt = CausalLoopEngine(self.build_spec(), [finisher]).run({"done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["requiredConvergenceEffects"], [])
        self.assertEqual(receipt["missingConvergenceEffects"], [])
        self.assertTrue(receipt["convergenceRequirementsPassed"])

    def test_declared_effect_alone_cannot_replace_raw_end_truth(self):
        marker = Module(
            "marker",
            "0.01",
            ("touched",),
            lambda s: not s["touched"],
            lambda _s: {"touched": True},
            authority_scope=("touched",),
            convergence_effects=("world_finished",),
        )
        receipt = CausalLoopEngine(
            self.build_spec(required=("world_finished",)), [marker]
        ).run({"done": False, "touched": False})

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "no_relevant_module")
        self.assertEqual(receipt["realizedConvergenceEffects"], ["world_finished"])
        self.assertFalse(receipt["rawEndInvariantPassed"])
        self.assertFalse(receipt["convergenceRequirementsPassed"])

    def test_registered_but_unrealized_effect_cannot_authorize_raw_endpoint(self):
        bypass = Module(
            "bypass",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        proof = Module(
            "proof",
            "0.01",
            ("proof.enabled",),
            lambda _s: False,
            lambda _s: {"proof.enabled": True},
            authority_scope=("proof.enabled",),
            convergence_effects=("world_finished",),
        )
        start = {"done": False, "proof.enabled": False}
        receipt = CausalLoopEngine(
            self.build_spec(required=("world_finished",)), [bypass, proof]
        ).run(start)

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureReason"], "unsatisfied_convergence_effects")
        self.assertTrue(receipt["rawEndInvariantPassed"])
        self.assertFalse(receipt["convergenceRequirementsPassed"])
        self.assertEqual(receipt["realizedConvergenceEffects"], [])
        self.assertEqual(receipt["missingConvergenceEffects"], ["world_finished"])
        self.assertTrue(receipt["endState"]["done"])
        self.assertTrue(receipt["convergenceEffectBlocks"])

    def test_committed_effect_plus_raw_endpoint_converges(self):
        finisher = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=("world_finished",),
        )
        receipt = CausalLoopEngine(
            self.build_spec(required=("world_finished",)), [finisher]
        ).run({"done": False})

        self.assertEqual(receipt["status"], "converged")
        self.assertTrue(receipt["rawEndInvariantPassed"])
        self.assertTrue(receipt["convergenceRequirementsPassed"])
        self.assertEqual(receipt["realizedConvergenceEffects"], ["world_finished"])
        self.assertEqual(receipt["missingConvergenceEffects"], [])

    def test_unknown_required_effect_is_rejected_at_engine_construction(self):
        finisher = Module(
            "finisher",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        with self.assertRaisesRegex(ValueError, "not declared by any module"):
            CausalLoopEngine(self.build_spec(required=("missing",)), [finisher])

    def test_duplicate_or_blank_effect_declarations_are_rejected(self):
        duplicate = Module(
            "duplicate",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=("finish", "finish"),
        )
        blank = Module(
            "blank",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            convergence_effects=("",),
        )
        with self.assertRaisesRegex(ValueError, "duplicate convergence effects"):
            CausalLoopEngine(self.build_spec(), [duplicate])
        with self.assertRaisesRegex(ValueError, "invalid convergence effect"):
            CausalLoopEngine(self.build_spec(), [blank])
        with self.assertRaisesRegex(ValueError, "required convergence effects must be unique"):
            CausalLoopEngine(
                self.build_spec(required=("finish", "finish")),
                [Module(
                    "finish",
                    "0.01",
                    ("done",),
                    lambda s: not s["done"],
                    lambda _s: {"done": True},
                    authority_scope=("done",),
                    convergence_effects=("finish",),
                )],
            )

    def test_unsatisfied_effect_failure_replays_deterministically(self):
        bypass = Module(
            "bypass",
            "0.01",
            ("done",),
            lambda s: not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
        )
        proof = Module(
            "proof",
            "0.01",
            ("proof.enabled",),
            lambda _s: False,
            lambda _s: {"proof.enabled": True},
            authority_scope=("proof.enabled",),
            convergence_effects=("world_finished",),
        )
        engine = CausalLoopEngine(
            self.build_spec(required=("world_finished",)), [bypass, proof]
        )
        start = {"done": False, "proof.enabled": False}
        first = engine.run(start)
        second = engine.run(start)
        replay = engine.replay(first)

        self.assertEqual(first["receiptHash"], second["receiptHash"])
        self.assertEqual(first["convergenceEffectBlocks"], second["convergenceEffectBlocks"])
        self.assertTrue(replay["replayMatches"])

    def test_checkpoint_preserves_realized_effect_evidence(self):
        marker = Module(
            "marker",
            "0.01",
            ("touched",),
            lambda s: not s["touched"],
            lambda _s: {"touched": True},
            authority_scope=("touched",),
            convergence_effects=("world_finished",),
        )
        finisher = Module(
            "finisher",
            "0.01",
            ("touched", "done"),
            lambda s: s["touched"] and not s["done"],
            lambda _s: {"done": True},
            authority_scope=("done",),
            dependencies=("marker",),
        )
        engine = CausalLoopEngine(
            self.build_spec(required=("world_finished",)), [marker, finisher]
        )
        start = {"done": False, "touched": False}
        checkpoint = engine.pause(start, after_waves=1)
        resumed = engine.resume(checkpoint)
        uninterrupted = engine.run(start)

        self.assertEqual(checkpoint["realizedConvergenceEffects"], ["world_finished"])
        self.assertEqual(resumed["receiptHash"], uninterrupted["receiptHash"])
        self.assertTrue(resumed["convergenceRequirementsPassed"])

    def test_train_requires_and_realizes_departure_effect(self):
        receipt = build_engine().run(initial_state())

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["requiredConvergenceEffects"], ["train_departed"])
        self.assertEqual(receipt["realizedConvergenceEffects"], ["train_departed"])
        self.assertTrue(receipt["convergenceRequirementsPassed"])
        self.assertIn("12-train-depart", receipt["modulesActivated"])


if __name__ == "__main__":
    unittest.main()
