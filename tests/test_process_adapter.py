import io
import json
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from causal_loop.engine import deterministic_hash
from causal_loop.process_adapter import (
    REQUEST_SCHEMA,
    capability_descriptor,
    process_request,
    run_stream,
)


ROOT = Path(__file__).resolve().parents[1]


def run_request(request_id="run-1"):
    return {
        "schema": REQUEST_SCHEMA,
        "requestId": request_id,
        "op": "run",
        "timedInfluences": [
            {"atWave": 2, "action": "BLOCK_DOOR"},
            {"atWave": 3, "action": "TRIGGER_ALARM"},
        ],
        "maxWaves": 64,
    }


class ProcessAdapterTests(unittest.TestCase):
    def test_descriptor_file_matches_live_contract(self):
        descriptor = json.loads((ROOT / "capabilities/causal-loop-process-v1.json").read_text())
        self.assertEqual(descriptor, capability_descriptor())

    def test_same_request_produces_same_verified_receipt(self):
        first = process_request(run_request())
        second = process_request(run_request())
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")
        self.assertTrue(first["replayMatches"])
        self.assertEqual(first["receipt"]["status"], "converged")
        self.assertFalse(first["receipt"]["committed"])
        self.assertEqual(first["receipt"]["endState"]["train.departureDelay"], 3)

    def test_verify_accepts_an_unchanged_receipt(self):
        receipt = process_request(run_request())["receipt"]
        response = process_request(
            {"schema": REQUEST_SCHEMA, "requestId": "verify-1", "op": "verify", "receipt": receipt}
        )
        self.assertEqual(response["status"], "PASS")
        self.assertTrue(response["replayMatches"])
        self.assertEqual(response["verifiedReceiptHash"], receipt["receiptHash"])

    def test_bounded_failure_keeps_a_replayable_receipt(self):
        request = run_request("bounded-failure")
        request["maxWaves"] = 1
        response = process_request(request)
        self.assertEqual(response["status"], "HOLD")
        self.assertEqual(response["executionStatus"], "failed")
        self.assertEqual(response["executionMaxWaves"], 1)
        self.assertTrue(response["replayMatches"])

        verified = process_request(
            {
                "schema": REQUEST_SCHEMA,
                "requestId": "verify-bounded-failure",
                "op": "verify",
                "receipt": response["receipt"],
                "maxWaves": response["executionMaxWaves"],
            }
        )
        self.assertEqual(verified["status"], "PASS")
        self.assertEqual(verified["executionStatus"], "failed")

    def test_byte_tampering_fails_integrity(self):
        receipt = deepcopy(process_request(run_request())["receipt"])
        receipt["endState"]["train.departureDelay"] = 999
        response = process_request(
            {"schema": REQUEST_SCHEMA, "requestId": "verify-tampered", "op": "verify", "receipt": receipt}
        )
        self.assertEqual(response["status"], "HOLD")
        self.assertEqual(response["error"]["code"], "receipt_integrity_mismatch")

    def test_resealed_false_receipt_fails_replay(self):
        receipt = deepcopy(process_request(run_request())["receipt"])
        receipt["endStateHash"] = "0" * 64
        receipt["receiptHash"] = deterministic_hash(
            {key: value for key, value in receipt.items() if key != "receiptHash"}
        )
        response = process_request(
            {"schema": REQUEST_SCHEMA, "requestId": "verify-resealed", "op": "verify", "receipt": receipt}
        )
        self.assertEqual(response["status"], "HOLD")
        self.assertEqual(response["error"]["code"], "receipt_replay_mismatch")

    def test_unknown_fields_and_actions_fail_closed(self):
        unknown_field = run_request("unknown-field")
        unknown_field["consequence"] = "SET_TRAIN_DELAYED_TRUE"
        self.assertEqual(process_request(unknown_field)["error"]["code"], "unknown_field")

        unknown_action = run_request("unknown-action")
        unknown_action["timedInfluences"][0]["action"] = "SET_TRAIN_DELAYED_TRUE"
        self.assertEqual(process_request(unknown_action)["error"]["code"], "unsupported_action")

    def test_repeated_timed_influence_preserves_engine_sequence(self):
        request = run_request("repeated-action")
        request["timedInfluences"] = [
            {"atWave": 2, "action": "TRIGGER_ALARM"},
            {"atWave": 2, "action": "TRIGGER_ALARM"},
        ]
        response = process_request(request)
        self.assertEqual(response["status"], "PASS")
        self.assertEqual(len(response["receipt"]["timedExternalInfluences"]), 2)
        self.assertEqual(
            [item["sequence"] for item in response["receipt"]["timedExternalInfluences"]],
            [0, 1],
        )

    def test_stream_reports_bad_line_and_continues(self):
        valid = {"schema": REQUEST_SCHEMA, "requestId": "describe-1", "op": "describe"}
        stdin = io.StringIO("{bad json}\n" + json.dumps(valid) + "\n")
        stdout = io.StringIO()
        self.assertEqual(run_stream(stdin, stdout), 1)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([item["status"] for item in responses], ["HOLD", "PASS"])
        self.assertEqual(responses[0]["error"]["code"], "invalid_json")

    def test_stream_rejects_duplicate_keys_and_non_finite_numbers(self):
        stdin = io.StringIO(
            '{"schema":"x","schema":"y","requestId":"duplicate","op":"describe"}\n'
            '{"schema":"x","requestId":"nan","op":"run","timedInfluences":[],"maxWaves":NaN}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(run_stream(stdin, stdout), 1)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([item["error"]["code"] for item in responses], ["invalid_json", "invalid_json"])

    def test_entrypoint_runs_from_an_external_working_directory(self):
        command = [sys.executable, str(ROOT / "scripts/causal_loop_ndjson.py")]
        request = json.dumps(run_request("external-cwd"), sort_keys=True) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                command,
                cwd=directory,
                input=request,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        response = json.loads(completed.stdout)
        self.assertEqual(response["status"], "PASS")
        self.assertTrue(response["replayMatches"])


if __name__ == "__main__":
    unittest.main()
