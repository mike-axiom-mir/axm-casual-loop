from copy import deepcopy
import unittest

from causal_loop.engine import commit_receipt_to_history, deterministic_hash
from causal_loop.train_platform import build_engine, initial_state


class PersistentHistoryAdmissionTests(unittest.TestCase):
    def committed_receipt(self):
        return build_engine().run(initial_state(), ["BLOCK_DOOR"], commit=True)

    def reseal(self, receipt):
        receipt.pop("receiptHash", None)
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def test_valid_current_receipt_is_admitted(self):
        receipt = self.committed_receipt()
        history = []

        commit_receipt_to_history(receipt, history)

        self.assertEqual(history, receipt["historyEffects"])

    def test_mutated_receipt_hash_is_rejected_before_history_changes(self):
        receipt = self.committed_receipt()
        receipt["historyEffects"][0]["endStateHash"] = "0" * 64
        history = []

        with self.assertRaisesRegex(ValueError, "receipt hash mismatch"):
            commit_receipt_to_history(receipt, history)

        self.assertEqual(history, [])

    def test_resealed_end_state_hash_drift_is_rejected(self):
        receipt = deepcopy(self.committed_receipt())
        receipt["endStateHash"] = "0" * 64
        receipt["historyEffects"][0]["endStateHash"] = "0" * 64
        self.reseal(receipt)
        history = []

        with self.assertRaisesRegex(ValueError, "end state hash mismatch"):
            commit_receipt_to_history(receipt, history)

        self.assertEqual(history, [])

    def test_resealed_history_effect_lineage_drift_is_rejected(self):
        receipt = deepcopy(self.committed_receipt())
        receipt["historyEffects"][0]["runId"] = "other-run"
        self.reseal(receipt)
        history = []

        with self.assertRaisesRegex(ValueError, "history effect lineage mismatch"):
            commit_receipt_to_history(receipt, history)

        self.assertEqual(history, [])

    def test_retrying_same_commit_is_idempotent(self):
        receipt = self.committed_receipt()
        history = []

        commit_receipt_to_history(receipt, history)
        commit_receipt_to_history(receipt, history)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0], receipt["historyEffects"][0])

    def test_conflicting_existing_commit_for_same_run_fails_closed(self):
        receipt = self.committed_receipt()
        conflict = deepcopy(receipt["historyEffects"][0])
        conflict["endStateHash"] = "f" * 64
        history = [conflict]

        with self.assertRaisesRegex(ValueError, "conflicting persistent history"):
            commit_receipt_to_history(receipt, history)

        self.assertEqual(history, [conflict])

    def test_uncommitted_receipt_remains_ineligible(self):
        receipt = build_engine().run(initial_state(), ["WAIT"], commit=False)
        history = []

        with self.assertRaisesRegex(ValueError, "only committed, converged"):
            commit_receipt_to_history(receipt, history)

        self.assertEqual(history, [])


if __name__ == "__main__":
    unittest.main()
