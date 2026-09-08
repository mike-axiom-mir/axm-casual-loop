from copy import deepcopy
import unittest

from causal_loop.engine import TimedInfluence
from causal_loop.observer import project_receipt
from causal_loop.train_platform import build_engine, initial_state


class ObserverProofTests(unittest.TestCase):
    def _receipt(self):
        return build_engine().run(
            initial_state(),
            timed_influences=[
                TimedInfluence(2, "BLOCK_DOOR"),
                TimedInfluence(3, "TRIGGER_ALARM"),
            ],
        )

    def test_projection_reaches_authoritative_start_and_end_hashes(self):
        receipt = self._receipt()
        projection = project_receipt(receipt)
        self.assertTrue(projection["observerOnly"])
        self.assertFalse(projection["authoritative"])
        self.assertEqual(projection["frames"][0]["stateHash"], receipt["startStateHash"])
        self.assertEqual(projection["frames"][-1]["stateHash"], receipt["endStateHash"])
        self.assertEqual(projection["authoritativeReceiptHash"], receipt["receiptHash"])

    def test_projection_does_not_mutate_source_receipt(self):
        receipt = self._receipt()
        before = deepcopy(receipt)
        project_receipt(receipt)
        self.assertEqual(receipt, before)

    def test_module_wave_is_visualized_atomically(self):
        receipt = build_engine().run(initial_state(), ["WAIT"])
        projection = project_receipt(receipt)
        wave_one = next(frame for frame in projection["frames"] if frame["kind"] == "wave" and frame["wave"] == 1)
        self.assertGreater(len(wave_one["sources"]), 1)
        self.assertIn("02-door-open", wave_one["sources"])
        self.assertIn("03-passenger-approach", wave_one["sources"])
        module_transitions = [item for item in receipt["stateTransitions"] if item["kind"] == "module"]
        wave_frames = [frame for frame in projection["frames"] if frame["kind"] == "wave"]
        self.assertLess(len(wave_frames), len(module_transitions))

    def test_tampered_transition_hash_is_rejected(self):
        receipt = self._receipt()
        tampered = deepcopy(receipt)
        transition = next(item for item in tampered["stateTransitions"] if item.get("stateHash"))
        transition["stateHash"] = "0" * 64
        with self.assertRaises(ValueError):
            project_receipt(tampered)

    def test_same_receipt_produces_same_projection_hash(self):
        receipt = self._receipt()
        first = project_receipt(receipt)
        second = project_receipt(receipt)
        self.assertEqual(first["projectionHash"], second["projectionHash"])
        self.assertEqual(first["frames"], second["frames"])


if __name__ == "__main__":
    unittest.main()
