from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest

from causal_loop import TimedInfluence, deterministic_hash
from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_resume import (
    CHECKPOINT_RESUME_EXECUTION_AUTHORITY,
    CHECKPOINT_RESUME_EXECUTION_SCHEMA,
    execute_checkpoint_resume,
    verify_checkpoint_resume_execution,
)
from causal_loop.checkpoint_selection import (
    CHECKPOINT_SELECTION_SCHEMA,
    prepare_checkpoint_resume,
)
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state


class CheckpointResumeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_engine()
        self.schedule = [
            TimedInfluence(2, "BLOCK_DOOR"),
            TimedInfluence(3, "TRIGGER_ALARM"),
        ]
        self.checkpoint = self.engine.pause(
            initial_state(), timed_influences=self.schedule, after_waves=2
        )

    def prepare(self, store: LocalCheckpointStore) -> dict:
        inventory = inspect_checkpoint_store(store)
        return prepare_checkpoint_resume(
            store,
            {
                "schema": CHECKPOINT_SELECTION_SCHEMA,
                "candidateSetHash": inventory["candidateSetHash"],
                "checkpointHash": self.checkpoint["checkpointHash"],
            },
        )

    def test_exact_plan_executes_only_through_prefix_admission_and_stays_uncommitted(self):
        uninterrupted = self.engine.run(
            initial_state(), timed_influences=self.schedule, commit=False
        )
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            plan = self.prepare(store)

            execution = execute_checkpoint_resume(
                self.engine,
                store,
                plan,
                expected_plan_hash=plan["receipt"]["planHash"],
            )

            self.assertEqual(execution["result"], uninterrupted)
            self.assertFalse(execution["result"]["committed"])
            self.assertEqual(
                execution["receipt"]["schema"], CHECKPOINT_RESUME_EXECUTION_SCHEMA
            )
            self.assertEqual(
                execution["receipt"]["authority"],
                CHECKPOINT_RESUME_EXECUTION_AUTHORITY,
            )
            self.assertEqual(
                execution["receipt"]["planHash"], plan["receipt"]["planHash"]
            )
            self.assertEqual(
                execution["receipt"]["resultReceiptHash"],
                uninterrupted["receiptHash"],
            )
            self.assertTrue(execution["receipt"]["resumeExecuted"])
            self.assertFalse(execution["receipt"]["historyCommitted"])

    def test_stale_or_tampered_plan_is_rejected_before_engine_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            plan = self.prepare(store)
            tampered = deepcopy(plan)
            tampered["checkpoint"]["wavesExecuted"] += 1

            calls = 0
            original_resume = self.engine.resume

            def counted_resume(*args, **kwargs):
                nonlocal calls
                calls += 1
                return original_resume(*args, **kwargs)

            self.engine.resume = counted_resume
            with self.assertRaisesRegex(ValueError, "deterministic replay"):
                execute_checkpoint_resume(self.engine, store, tampered)
            self.assertEqual(calls, 0)

    def test_wrong_engine_contract_fails_at_existing_checkpoint_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            plan = self.prepare(store)
            wrong_engine = build_engine()
            wrong_engine.spec = deepcopy(wrong_engine.spec)
            object.__setattr__(wrong_engine.spec, "version", "different-engine-version")

            with self.assertRaises(ValueError):
                execute_checkpoint_resume(wrong_engine, store, plan)

    def test_execution_verifier_replays_store_plan_and_result_with_optional_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.checkpoint)
            plan = self.prepare(store)
            execution = execute_checkpoint_resume(self.engine, store, plan)

            verified = verify_checkpoint_resume_execution(
                self.engine,
                store,
                plan,
                execution,
                expected_execution_hash=execution["receipt"]["executionHash"],
            )
            self.assertTrue(verified["valid"])
            self.assertTrue(verified["resumeExecuted"])
            self.assertFalse(verified["historyCommitted"])

            tampered = deepcopy(execution)
            tampered["receipt"]["authority"] = "AUTOMATIC_RESUME_AND_COMMIT"
            unsigned = deepcopy(tampered["receipt"])
            unsigned.pop("executionHash")
            tampered["receipt"]["executionHash"] = deterministic_hash(unsigned)
            with self.assertRaisesRegex(ValueError, "deterministic replay"):
                verify_checkpoint_resume_execution(
                    self.engine, store, plan, tampered
                )

            with self.assertRaisesRegex(ValueError, "caller-pinned"):
                verify_checkpoint_resume_execution(
                    self.engine,
                    store,
                    plan,
                    execution,
                    expected_execution_hash="0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
