from __future__ import annotations

import json
from threading import Thread
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from causal_loop import TimedInfluence
from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_selection import CHECKPOINT_SELECTION_SCHEMA
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state
from tools.checkpoint_recovery_station import RecoveryStation, build_server


class CheckpointRecoveryStationTests(unittest.TestCase):
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

    def test_station_projects_real_inventory_and_prepares_only_explicit_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            store.save(self.second)
            station = RecoveryStation(store)

            inventory = station.inventory()
            self.assertEqual(inventory["candidateCount"], 2)
            self.assertNotIn("selected", inventory)
            self.assertNotIn("latest", inventory)

            plan = station.prepare(
                self.selection(inventory, self.second["checkpointHash"])
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
            self.assertNotIn("resumeExecuted", plan["receipt"])

    def test_http_selection_fails_closed_after_candidate_set_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCheckpointStore(directory)
            store.save(self.first)
            server = build_server(directory, port=0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(f"{base}/api/inventory", timeout=3) as response:
                    inventory = json.load(response)
                store.save(self.second)
                payload = json.dumps(
                    self.selection(inventory, self.first["checkpointHash"])
                ).encode("utf-8")
                request = Request(
                    f"{base}/api/prepare",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as held:
                    urlopen(request, timeout=3)
                self.assertEqual(held.exception.code, 409)
                response = json.loads(held.exception.read().decode("utf-8"))
                self.assertIn("candidate set changed", response["error"])
                self.assertEqual(response["inventory"]["candidateCount"], 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_server_refuses_non_loopback_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "loopback-only"):
                build_server(directory, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
