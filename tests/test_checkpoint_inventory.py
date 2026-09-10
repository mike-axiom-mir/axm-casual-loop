from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from causal_loop import TimedInfluence
from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state


class CheckpointInventoryTests(unittest.TestCase):
    def setUp(self):
        engine = build_engine()
        schedule = [
            TimedInfluence(2, "BLOCK_DOOR"),
            TimedInfluence(3, "TRIGGER_ALARM"),
        ]
        self.first = engine.pause(
            initial_state(),
            timed_influences=schedule,
            after_waves=1,
        )
        self.second = engine.pause(
            initial_state(),
            timed_influences=schedule,
            after_waves=2,
        )
        self.assertNotEqual(self.first["checkpointHash"], self.second["checkpointHash"])

    def test_fresh_process_can_reconstruct_candidates_without_latest_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)

            script = """
import json
import sys
from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_store import LocalCheckpointStore

inventory = inspect_checkpoint_store(LocalCheckpointStore(sys.argv[1]))
print(json.dumps({
    "candidateSetHash": inventory["candidateSetHash"],
    "candidates": inventory["candidates"],
    "authority": inventory["authority"],
}, sort_keys=True))
"""
            completed = subprocess.run(
                [sys.executable, "-c", script, directory],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            observed = json.loads(completed.stdout)

            expected_hashes = sorted(
                [self.first["checkpointHash"], self.second["checkpointHash"]]
            )
            self.assertEqual(
                [item["checkpointHash"] for item in observed["candidates"]],
                expected_hashes,
            )
            self.assertEqual(
                observed["authority"],
                "DERIVED_DISCOVERY_ONLY_NO_SELECTION_NO_RESUME_NO_CANON",
            )
            self.assertNotIn("latest", observed)
            self.assertNotIn("selectedCheckpointHash", observed)

    def test_inventory_is_small_projection_not_second_canonical_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.second)
            inventory = inspect_checkpoint_store(store)

            self.assertEqual(inventory["candidateCount"], 1)
            candidate = inventory["candidates"][0]
            self.assertEqual(candidate["checkpointHash"], self.second["checkpointHash"])
            self.assertEqual(candidate["stateHash"], self.second["stateHash"])
            self.assertEqual(candidate["wavesExecuted"], self.second["wavesExecuted"])
            self.assertNotIn("state", candidate)
            self.assertNotIn("startState", candidate)
            self.assertNotIn("transitions", candidate)

    def test_corrupt_final_is_held_without_hiding_other_valid_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)
            corrupt_path = Path(directory) / f"{self.first['checkpointHash']}.json"
            corrupt_path.write_bytes(b"{}")

            inventory = inspect_checkpoint_store(store)

            self.assertEqual(inventory["candidateCount"], 1)
            self.assertEqual(
                inventory["candidates"][0]["checkpointHash"],
                self.second["checkpointHash"],
            )
            self.assertEqual(
                inventory["held"],
                [
                    {
                        "checkpointHash": self.first["checkpointHash"],
                        "reason": "CHECKPOINT_ADMISSION_FAILED",
                    }
                ],
            )

    def test_symlink_named_like_checkpoint_is_held_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            real_path = Path(directory) / f"{self.first['checkpointHash']}.json"
            fake_id = "0" * 64
            (Path(directory) / f"{fake_id}.json").symlink_to(real_path.name)

            inventory = inspect_checkpoint_store(store)

            self.assertEqual(inventory["candidateCount"], 1)
            self.assertEqual(inventory["heldCount"], 1)
            self.assertEqual(inventory["held"][0]["checkpointHash"], fake_id)
            self.assertEqual(
                inventory["held"][0]["reason"], "CHECKPOINT_ADMISSION_FAILED"
            )

    def test_non_candidates_do_not_change_candidate_identity_or_gain_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            baseline = inspect_checkpoint_store(store)

            root = Path(directory)
            (root / "latest.json").write_text("{}", encoding="utf-8")
            (root / "notes.txt").write_text("not checkpoint state", encoding="utf-8")
            (root / f".{self.first['checkpointHash']}.abandoned.tmp").write_bytes(b"partial")
            observed = inspect_checkpoint_store(store)

            self.assertEqual(observed["candidateSetHash"], baseline["candidateSetHash"])
            self.assertEqual(observed["candidates"], baseline["candidates"])
            self.assertEqual(observed["held"], [])
            self.assertEqual(observed["diagnostics"]["abandonedTempCount"], 1)
            self.assertEqual(observed["diagnostics"]["ignoredEntryCount"], 2)

    def test_candidate_set_hash_changes_only_when_verified_candidate_set_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            one = inspect_checkpoint_store(store)
            store.save(self.second)
            two = inspect_checkpoint_store(store)

            self.assertNotEqual(one["candidateSetHash"], two["candidateSetHash"])
            self.assertEqual(one["candidateCount"], 1)
            self.assertEqual(two["candidateCount"], 2)


if __name__ == "__main__":
    unittest.main()
