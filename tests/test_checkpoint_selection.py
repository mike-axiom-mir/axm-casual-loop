from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from causal_loop import TimedInfluence, deterministic_hash
from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_selection import (
    CHECKPOINT_SELECTION_SCHEMA,
    prepare_checkpoint_resume,
    verify_checkpoint_resume_plan,
)
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state


class CheckpointSelectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_engine()
        self.schedule = [
            TimedInfluence(2, "BLOCK_DOOR"),
            TimedInfluence(3, "TRIGGER_ALARM"),
        ]
        self.first = self.engine.pause(
            initial_state(), timed_influences=self.schedule, after_waves=1
        )
        self.second = self.engine.pause(
            initial_state(), timed_influences=self.schedule, after_waves=2
        )

    @staticmethod
    def selection(inventory: dict, checkpoint_hash: str) -> dict:
        return {
            "schema": CHECKPOINT_SELECTION_SCHEMA,
            "candidateSetHash": inventory["candidateSetHash"],
            "checkpointHash": checkpoint_hash,
        }

    def test_exact_caller_choice_prepares_resume_without_selecting_or_resuming(self):
        uninterrupted = self.engine.run(
            initial_state(), timed_influences=self.schedule
        )
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)
            inventory = inspect_checkpoint_store(store)

            plan = prepare_checkpoint_resume(
                store, self.selection(inventory, self.second["checkpointHash"])
            )

            self.assertEqual(plan["checkpoint"], self.second)
            self.assertEqual(
                plan["receipt"]["selection"]["checkpointHash"],
                self.second["checkpointHash"],
            )
            self.assertEqual(
                plan["receipt"]["authority"],
                "EXPLICIT_SELECTION_ONLY_NO_AUTOMATIC_SELECTION_NO_RESUME_NO_CANON",
            )
            self.assertNotIn("latest", plan["receipt"])
            self.assertNotIn("state", plan["receipt"]["candidate"])

            resumed = self.engine.resume(plan["checkpoint"])
            self.assertEqual(resumed["receiptHash"], uninterrupted["receiptHash"])

    def test_fresh_process_prepares_only_the_pinned_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)
            selection = self.selection(
                inspect_checkpoint_store(store), self.first["checkpointHash"]
            )
            script = """
import json
import sys
from causal_loop.checkpoint_selection import prepare_checkpoint_resume
from causal_loop.checkpoint_store import LocalCheckpointStore

plan = prepare_checkpoint_resume(LocalCheckpointStore(sys.argv[1]), json.loads(sys.argv[2]))
print(json.dumps({
    "checkpointHash": plan["checkpoint"]["checkpointHash"],
    "planHash": plan["receipt"]["planHash"],
    "authority": plan["receipt"]["authority"],
}, sort_keys=True))
"""
            completed = subprocess.run(
                [sys.executable, "-c", script, directory, json.dumps(selection)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            observed = json.loads(completed.stdout)
            self.assertEqual(observed["checkpointHash"], self.first["checkpointHash"])
            self.assertRegex(observed["planHash"], r"^[0-9a-f]{64}$")

    def test_candidate_set_change_invalidates_stale_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            stale = self.selection(
                inspect_checkpoint_store(store), self.first["checkpointHash"]
            )
            store.save(self.second)

            with self.assertRaisesRegex(ValueError, "candidate set changed"):
                prepare_checkpoint_resume(store, stale)

    def test_missing_or_held_checkpoint_cannot_be_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            held_hash = "0" * 64
            (Path(directory) / f"{held_hash}.json").write_text("{}", encoding="utf-8")
            inventory = inspect_checkpoint_store(store)

            with self.assertRaisesRegex(ValueError, "not a verified candidate"):
                prepare_checkpoint_resume(store, self.selection(inventory, held_hash))

            plan = prepare_checkpoint_resume(
                store, self.selection(inventory, self.first["checkpointHash"])
            )
            self.assertEqual(plan["checkpoint"], self.first)

    def test_selection_contract_rejects_implicit_or_ambiguous_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            inventory = inspect_checkpoint_store(store)
            exact = self.selection(inventory, self.first["checkpointHash"])

            with self.assertRaisesRegex(ValueError, "exactly"):
                prepare_checkpoint_resume(store, {**exact, "latest": True})
            with self.assertRaisesRegex(ValueError, "exactly"):
                prepare_checkpoint_resume(
                    store,
                    {
                        "schema": CHECKPOINT_SELECTION_SCHEMA,
                        "candidateSetHash": inventory["candidateSetHash"],
                    },
                )
            with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
                prepare_checkpoint_resume(
                    store, {**exact, "checkpointHash": "latest"}
                )

    def test_plan_verifier_replays_store_and_supports_caller_pinning(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)
            inventory = inspect_checkpoint_store(store)
            first_plan = prepare_checkpoint_resume(
                store, self.selection(inventory, self.first["checkpointHash"])
            )
            second_plan = prepare_checkpoint_resume(
                store, self.selection(inventory, self.second["checkpointHash"])
            )

            verified = verify_checkpoint_resume_plan(
                store, first_plan, first_plan["receipt"]["planHash"]
            )
            self.assertTrue(verified["valid"])
            self.assertEqual(
                verified["checkpointHash"], self.first["checkpointHash"]
            )
            self.assertTrue(verify_checkpoint_resume_plan(store, second_plan)["valid"])
            with self.assertRaisesRegex(ValueError, "caller-pinned"):
                verify_checkpoint_resume_plan(
                    store, second_plan, first_plan["receipt"]["planHash"]
                )

            tampered = deepcopy(first_plan)
            tampered["receipt"]["authority"] = "AUTO_RESUME"
            unsigned = deepcopy(tampered["receipt"])
            unsigned.pop("planHash")
            tampered["receipt"]["planHash"] = deterministic_hash(unsigned)
            with self.assertRaisesRegex(ValueError, "deterministic replay"):
                verify_checkpoint_resume_plan(store, tampered)


if __name__ == "__main__":
    unittest.main()
