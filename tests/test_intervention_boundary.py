import unittest

from causal_loop.engine import CausalLoopEngine, Invariant, LoopSpec, Module
from causal_loop.train_platform import intervention_handler, initial_state


DIRECTION_KEYS = {
    "player.blockingDoor",
    "player.triggerAlarm",
    "player.talkingToPassenger",
}


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

    def test_train_direction_handler_cannot_declare_delay_consequence(self):
        writes = dict(intervention_handler("BLOCK_DOOR", initial_state()))
        self.assertEqual(writes, {"player.blockingDoor": True})
        self.assertNotIn("delay.block", writes)
        self.assertNotIn("train.departureDelay", writes)

    def test_generic_engine_currently_trusts_intervention_handler_too_much(self):
        """Known gap: a LoopSpec handler can currently write authoritative state directly.

        This test intentionally passes while the gap exists. Flip it when the executor gains
        an engine-level intervention write scope rather than deleting the evidence.
        """

        consequence_key = "world.finished"
        spec = LoopSpec(
            loop_id="test.intervention-authority-gap/v0.01",
            version="0.01",
            start_invariant=Invariant("start", lambda s: not s[consequence_key], "start"),
            end_invariant=Invariant("end", lambda s: s[consequence_key], "hard_end"),
            hard_invariants=(),
            soft_invariants=(),
            intervention_handler=lambda action, _state: (
                {consequence_key: True} if action == "FINISH_WORLD" else {}
            ),
            max_waves=2,
        )
        never_needed = Module(
            "never-needed",
            "0.01",
            (consequence_key,),
            lambda _s: False,
            lambda _s: {},
            authority_scope=(),
        )
        receipt = CausalLoopEngine(spec, [never_needed]).run(
            {consequence_key: False},
            ["FINISH_WORLD"],
        )

        self.assertEqual(receipt["status"], "converged")
        self.assertEqual(receipt["modulesActivated"], [])
        self.assertTrue(receipt["endState"][consequence_key])
        external = next(item for item in receipt["stateTransitions"] if item["kind"] == "external")
        self.assertEqual(external["writes"], {consequence_key: True})


if __name__ == "__main__":
    unittest.main()
