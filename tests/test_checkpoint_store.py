from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from causal_loop import TimedInfluence, deterministic_hash
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state


class CheckpointStoreTests(unittest.TestCase):
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

    def test_checkpoint_survives_fresh_process_and_resumes_exactly(self):
        uninterrupted = self.engine.run(
            initial_state(), timed_influences=self.schedule
        )
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            saved = store.save(self.checkpoint)
            self.assertTrue(saved["created"])
            self.assertEqual(saved["checkpointHash"], self.checkpoint["checkpointHash"])
            self.assertEqual(saved["authority"], "STORAGE_ONLY_NO_RESUME_NO_CANON")

            script = """
import json
import sys
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine

store = LocalCheckpointStore(sys.argv[1])
checkpoint = store.load(sys.argv[2])
receipt = build_engine().resume(checkpoint)
print(json.dumps({"receiptHash": receipt["receiptHash"], "status": receipt["status"]}, sort_keys=True))
"""
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    directory,
                    self.checkpoint["checkpointHash"],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            resumed = json.loads(completed.stdout)
            self.assertEqual(resumed["status"], "converged")
            self.assertEqual(resumed["receiptHash"], uninterrupted["receiptHash"])

    def test_same_checkpoint_is_idempotent_and_exact_id_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            first = store.save(self.checkpoint)
            second = store.save(deepcopy(self.checkpoint))

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(store.load(self.checkpoint["checkpointHash"]), self.checkpoint)
            with self.assertRaisesRegex(ValueError, "checkpoint id"):
                store.load("latest")

    def test_checkpoint_hash_drift_is_rejected_before_write(self):
        forged = deepcopy(self.checkpoint)
        forged["state"]["platform.announcement"] = "forged"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            with self.assertRaisesRegex(ValueError, "checkpoint hash mismatch"):
                store.save(forged)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_corrupt_final_is_never_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            path = Path(directory) / f"{self.checkpoint['checkpointHash']}.json"
            corrupt = b'{"corrupt":true}\n'
            path.write_bytes(corrupt)

            with self.assertRaisesRegex(ValueError, "existing checkpoint bytes"):
                store.save(self.checkpoint)
            self.assertEqual(path.read_bytes(), corrupt)

    def test_load_rejects_noncanonical_or_tampered_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            path = Path(directory) / f"{self.checkpoint['checkpointHash']}.json"
            parsed = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "canonical checkpoint bytes"):
                store.load(self.checkpoint["checkpointHash"])

    def test_nonfinite_json_is_rejected_even_if_legacy_hash_is_resealed(self):
        forged = deepcopy(self.checkpoint)
        forged["state"]["train.departureDelay"] = float("nan")
        forged["stateHash"] = deterministic_hash(forged["state"])
        forged.pop("checkpointHash", None)
        forged["checkpointHash"] = deterministic_hash(forged)

        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            with self.assertRaisesRegex(ValueError, "strict portable JSON"):
                store.save(forged)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
