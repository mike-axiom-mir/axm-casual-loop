from __future__ import annotations

import unittest
from copy import deepcopy

from causal_loop import TimedInfluence, deterministic_hash
from causal_loop.train_platform import build_engine, initial_state


def reseal(checkpoint: dict) -> dict:
    checkpoint["stateHash"] = deterministic_hash(checkpoint["state"])
    checkpoint.pop("checkpointHash", None)
    checkpoint["checkpointHash"] = deterministic_hash(checkpoint)
    return checkpoint


class CheckpointPrefixAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_engine()
        self.schedule = [
            TimedInfluence(2, "BLOCK_DOOR"),
            TimedInfluence(3, "TRIGGER_ALARM"),
        ]
        self.checkpoint = self.engine.pause(
            initial_state(),
            timed_influences=self.schedule,
            after_waves=2,
        )

    def test_exact_checkpoint_still_resumes_to_uninterrupted_receipt(self):
        uninterrupted = self.engine.run(initial_state(), timed_influences=self.schedule)
        resumed = self.engine.resume(deepcopy(self.checkpoint))

        self.assertEqual(resumed["receiptHash"], uninterrupted["receiptHash"])
        self.assertEqual(resumed["stateTransitions"], uninterrupted["stateTransitions"])

    def test_resealed_impossible_state_prefix_is_rejected(self):
        forged = deepcopy(self.checkpoint)
        forged["state"]["platform.announcement"] = "forged causal prefix"

        with self.assertRaisesRegex(ValueError, "checkpoint causal prefix mismatch"):
            self.engine.resume(reseal(forged))

    def test_resealed_transition_prefix_is_rejected(self):
        forged = deepcopy(self.checkpoint)
        forged["stateTransitions"][0]["source"] = "forged-module"

        with self.assertRaisesRegex(ValueError, "checkpoint causal prefix mismatch"):
            self.engine.resume(reseal(forged))

    def test_resealed_activation_prefix_is_rejected(self):
        forged = deepcopy(self.checkpoint)
        forged["modulesActivated"].pop()

        with self.assertRaisesRegex(ValueError, "checkpoint causal prefix mismatch"):
            self.engine.resume(reseal(forged))

    def test_resealed_execution_metadata_is_rejected(self):
        mutations = {
            "appliedTimedInfluences": lambda value: value.append(
                {"atWave": 0, "sequence": 0, "action": "BLOCK_DOOR", "writes": {}}
            ),
            "convergencePath": lambda value: value.pop(),
            "seenCycleKeys": lambda value: value.pop(),
            "maxActiveWorkset": lambda _value: None,
        }

        for field, mutate in mutations.items():
            with self.subTest(field=field):
                forged = deepcopy(self.checkpoint)
                if field == "maxActiveWorkset":
                    forged[field] += 1
                else:
                    mutate(forged[field])
                with self.assertRaisesRegex(ValueError, "checkpoint causal prefix mismatch"):
                    self.engine.resume(reseal(forged))


if __name__ == "__main__":
    unittest.main()
