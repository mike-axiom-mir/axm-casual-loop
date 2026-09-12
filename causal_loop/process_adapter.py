from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from typing import Any, Mapping, TextIO

from .engine import TimedInfluence, canonical_json, deterministic_hash
from .train_platform import LOOP_ID, build_engine, initial_state

REQUEST_SCHEMA = "axm.causal-loop.process-request/v1"
RESPONSE_SCHEMA = "axm.causal-loop.process-response/v1"
CAPABILITY_SCHEMA = "axm.capability/v1"
CAPABILITY_ID = "axm.causal-loop.train-platform.process/v1"
ALLOWED_ACTIONS = ("WAIT", "BLOCK_DOOR", "TRIGGER_ALARM", "TALK_TO_PASSENGER")
MAX_TIMED_INFLUENCES = 64
MAX_WAVES_LIMIT = 256
MAX_LINE_BYTES = 1_048_576


class AdapterError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def capability_descriptor() -> dict[str, Any]:
    engine = build_engine()
    return {
        "schema": CAPABILITY_SCHEMA,
        "capabilityId": CAPABILITY_ID,
        "provider": {
            "repository": "mike-axiom-mir/axm-casual-loop",
            "module": "causal_loop.process_adapter",
            "entrypoint": "scripts/causal_loop_ndjson.py",
            "licenseFile": "LICENSE",
        },
        "protocol": {
            "transport": "ndjson-stdio",
            "requestSchema": REQUEST_SCHEMA,
            "responseSchema": RESPONSE_SCHEMA,
            "operations": ["describe", "run", "verify"],
        },
        "engine": {
            "loopId": LOOP_ID,
            "loopVersion": engine.spec.version,
            "receiptSchema": engine.spec.receipt_schema,
            "engineSignature": engine.engine_signature,
            "allowedActions": list(ALLOWED_ACTIONS),
            "maxTimedInfluences": MAX_TIMED_INFLUENCES,
            "maxWavesLimit": MAX_WAVES_LIMIT,
        },
        "properties": {
            "deterministic": True,
            "headless": True,
            "offline": True,
            "thirdPartyDependencies": False,
        },
        "authority": {
            "commitsHistory": False,
            "writesCanonicalState": False,
            "merges": False,
            "declaresCanon": False,
        },
    }


def _require_exact_keys(
    value: Mapping[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise AdapterError("missing_field", "missing field(s): " + ", ".join(missing))
    if unknown:
        raise AdapterError("unknown_field", "unknown field(s): " + ", ".join(unknown))


def _request_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise AdapterError("invalid_request_id", "requestId must be a non-empty string of at most 128 characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AdapterError("invalid_request_id", "requestId must contain valid Unicode") from exc
    return value


def _base_response(request_id: str | None, status: str) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "requestId": request_id,
        "status": status,
        "capabilityId": CAPABILITY_ID,
        "authority": capability_descriptor()["authority"],
    }


def _error_response(request_id: str | None, code: str, detail: str) -> dict[str, Any]:
    response = _base_response(request_id, "HOLD")
    response["error"] = {"code": code, "detail": detail}
    return response


def _normalize_timed_influences(value: Any) -> list[TimedInfluence]:
    if not isinstance(value, list):
        raise AdapterError("invalid_timed_influences", "timedInfluences must be an array")
    if len(value) > MAX_TIMED_INFLUENCES:
        raise AdapterError(
            "input_limit_exceeded",
            f"timedInfluences must contain at most {MAX_TIMED_INFLUENCES} items",
        )
    normalized: list[TimedInfluence] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AdapterError("invalid_timed_influence", f"timedInfluences[{index}] must be an object")
        _require_exact_keys(item, {"atWave", "action"})
        at_wave = item["atWave"]
        action = item["action"]
        if not isinstance(at_wave, int) or isinstance(at_wave, bool) or not 0 <= at_wave < MAX_WAVES_LIMIT:
            raise AdapterError(
                "invalid_wave",
                f"timedInfluences[{index}].atWave must be an integer from 0 to {MAX_WAVES_LIMIT - 1}",
            )
        if action not in ALLOWED_ACTIONS:
            raise AdapterError(
                "unsupported_action",
                f"timedInfluences[{index}].action must be one of: {', '.join(ALLOWED_ACTIONS)}",
            )
        normalized.append(TimedInfluence(at_wave, action))
    return normalized


def _max_waves(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_WAVES_LIMIT:
        raise AdapterError("invalid_max_waves", f"maxWaves must be an integer from 1 to {MAX_WAVES_LIMIT}")
    return value


def _verify_receipt(receipt: Any, *, max_waves: int = 64) -> tuple[dict[str, Any], str]:
    if not isinstance(receipt, Mapping):
        raise AdapterError("invalid_receipt", "receipt must be an object")
    candidate = deepcopy(dict(receipt))
    engine = build_engine(max_waves=max_waves)
    reference_keys = set(engine.run(initial_state()))
    if set(candidate) != reference_keys:
        missing = sorted(reference_keys - set(candidate))
        unknown = sorted(set(candidate) - reference_keys)
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if unknown:
            detail.append("unknown: " + ", ".join(unknown))
        raise AdapterError("receipt_shape_mismatch", "; ".join(detail))
    if candidate.get("schema") != engine.spec.receipt_schema:
        raise AdapterError("receipt_schema_mismatch", "receipt schema does not match the current engine")
    if candidate.get("loopId") != LOOP_ID or candidate.get("loopVersion") != engine.spec.version:
        raise AdapterError("receipt_engine_mismatch", "receipt loop identity does not match the current engine")
    supplied_hash = candidate.get("receiptHash")
    unhashed = {key: value for key, value in candidate.items() if key != "receiptHash"}
    expected_hash = deterministic_hash(unhashed)
    if supplied_hash != expected_hash:
        raise AdapterError("receipt_integrity_mismatch", "receiptHash does not match the receipt bytes")
    replayed = engine.replay(candidate)
    if not replayed.get("replayMatches"):
        raise AdapterError("receipt_replay_mismatch", "receipt does not reproduce on the current engine")
    return replayed, expected_hash


def process_request(request: Any) -> dict[str, Any]:
    request_id: str | None = None
    try:
        if not isinstance(request, Mapping):
            raise AdapterError("invalid_request", "request must be a JSON object")
        if "requestId" in request and isinstance(request["requestId"], str):
            request_id = request["requestId"]
        _require_exact_keys(request, {"schema", "requestId", "op"}, {"timedInfluences", "maxWaves", "receipt"})
        request_id = _request_id(request["requestId"])
        if request["schema"] != REQUEST_SCHEMA:
            raise AdapterError("request_schema_mismatch", f"schema must be {REQUEST_SCHEMA}")
        op = request["op"]
        if op == "describe":
            _require_exact_keys(request, {"schema", "requestId", "op"})
            response = _base_response(request_id, "PASS")
            response["capability"] = capability_descriptor()
            return response
        if op == "run":
            _require_exact_keys(
                request,
                {"schema", "requestId", "op", "timedInfluences"},
                {"maxWaves"},
            )
            timed = _normalize_timed_influences(request["timedInfluences"])
            max_waves = _max_waves(request.get("maxWaves", 64))
            engine = build_engine(max_waves=max_waves)
            receipt = engine.run(initial_state(), timed_influences=timed, commit=False)
            replayed, receipt_hash = _verify_receipt(receipt, max_waves=max_waves)
            passed = receipt["status"] == "converged" and bool(replayed["replayMatches"])
            response = _base_response(request_id, "PASS" if passed else "HOLD")
            response.update(
                {
                    "inputHash": deterministic_hash(
                        {
                            "timedInfluences": [item.contract(index) for index, item in enumerate(timed)],
                            "maxWaves": max_waves,
                        }
                    ),
                    "receiptHash": receipt_hash,
                    "executionMaxWaves": max_waves,
                    "executionStatus": receipt["status"],
                    "replayMatches": bool(replayed["replayMatches"]),
                    "receipt": receipt,
                }
            )
            return response
        if op == "verify":
            _require_exact_keys(
                request,
                {"schema", "requestId", "op", "receipt"},
                {"maxWaves"},
            )
            max_waves = _max_waves(request.get("maxWaves", 64))
            replayed, receipt_hash = _verify_receipt(
                request["receipt"], max_waves=max_waves
            )
            response = _base_response(request_id, "PASS")
            response.update(
                {
                    "verifiedReceiptHash": receipt_hash,
                    "replayedReceiptHash": replayed["receiptHash"],
                    "executionMaxWaves": max_waves,
                    "executionStatus": replayed["status"],
                    "replayMatches": True,
                }
            )
            return response
        raise AdapterError("unsupported_operation", "op must be one of: describe, run, verify")
    except AdapterError as exc:
        return _error_response(request_id, exc.code, exc.detail)
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        return _error_response(request_id, "invalid_request", str(exc))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate object key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def run_stream(stdin: TextIO, stdout: TextIO) -> int:
    held = False
    for raw_line in stdin:
        if not raw_line.strip():
            continue
        if len(raw_line.encode("utf-8")) > MAX_LINE_BYTES:
            response = _error_response(None, "line_limit_exceeded", f"input line exceeds {MAX_LINE_BYTES} bytes")
        else:
            try:
                request = json.loads(
                    raw_line,
                    object_pairs_hook=_strict_object,
                    parse_constant=_reject_json_constant,
                )
            except (json.JSONDecodeError, RecursionError, ValueError) as exc:
                if isinstance(exc, json.JSONDecodeError):
                    detail = f"invalid JSON at column {exc.colno}"
                else:
                    detail = str(exc)
                response = _error_response(None, "invalid_json", detail)
            else:
                response = process_request(request)
        held = held or response["status"] != "PASS"
        stdout.write(canonical_json(response) + "\n")
        stdout.flush()
    return 1 if held else 0


def main(argv: list[str] | None = None, *, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AXM train-platform causal loop over NDJSON stdio.")
    parser.parse_args(argv)
    return run_stream(stdin or sys.stdin, stdout or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
