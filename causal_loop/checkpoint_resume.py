from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .checkpoint_selection import verify_checkpoint_resume_plan
from .checkpoint_store import LocalCheckpointStore
from .engine import CausalLoopEngine, deterministic_hash

CHECKPOINT_RESUME_EXECUTION_SCHEMA = (
    "axm.causal-loop.checkpoint-resume-execution/v0.01"
)
CHECKPOINT_RESUME_EXECUTION_VERIFICATION_SCHEMA = (
    "axm.causal-loop.checkpoint-resume-execution-verification/v0.01"
)
CHECKPOINT_RESUME_EXECUTION_AUTHORITY = (
    "EXPLICIT_PLAN_EXECUTION_ONLY_NO_AUTOMATIC_SELECTION_NO_HISTORY_NO_CANON"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_KEYS = {"result", "receipt"}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "planHash",
    "checkpointHash",
    "resultReceiptHash",
    "resultStatus",
    "resultCommitted",
    "resumeExecuted",
    "historyCommitted",
    "authority",
    "executionHash",
}


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _validate_result_receipt(result: Any) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("resume result must be a mapping")
    exact = deepcopy(dict(result))
    receipt_hash = _require_sha256(exact.get("receiptHash"), "result receiptHash")
    unsigned = deepcopy(exact)
    unsigned.pop("receiptHash")
    if deterministic_hash(unsigned) != receipt_hash:
        raise ValueError("resume result receipt hash mismatch")
    if exact.get("committed") is not False:
        raise ValueError("checkpoint resume execution must remain uncommitted")
    if not isinstance(exact.get("status"), str) or not exact["status"]:
        raise ValueError("resume result status is invalid")
    return exact


def execute_checkpoint_resume(
    engine: CausalLoopEngine,
    store: LocalCheckpointStore,
    plan: Mapping[str, Any],
    *,
    expected_plan_hash: str | None = None,
) -> dict[str, Any]:
    """Execute one exact verified resume plan without committing persistent history.

    The plan verifier re-reads the content-addressed store before any engine work.
    The engine's existing resume path remains authoritative for checkpoint-prefix
    admission. This adapter has no selection, history, persistence, or CANON authority.
    """

    if not isinstance(engine, CausalLoopEngine):
        raise TypeError("engine must be a CausalLoopEngine")
    if not isinstance(store, LocalCheckpointStore):
        raise TypeError("store must be a LocalCheckpointStore")

    verification = verify_checkpoint_resume_plan(
        store, plan, expected_plan_hash=expected_plan_hash
    )
    checkpoint = deepcopy(dict(plan)["checkpoint"])
    result = _validate_result_receipt(engine.resume(checkpoint, commit=False))

    receipt_body = {
        "schema": CHECKPOINT_RESUME_EXECUTION_SCHEMA,
        "status": "RESUME_EXECUTED_UNCOMMITTED",
        "planHash": verification["planHash"],
        "checkpointHash": verification["checkpointHash"],
        "resultReceiptHash": result["receiptHash"],
        "resultStatus": result["status"],
        "resultCommitted": False,
        "resumeExecuted": True,
        "historyCommitted": False,
        "authority": CHECKPOINT_RESUME_EXECUTION_AUTHORITY,
    }
    receipt = {
        **receipt_body,
        "executionHash": deterministic_hash(receipt_body),
    }
    return {"result": result, "receipt": receipt}


def verify_checkpoint_resume_execution(
    engine: CausalLoopEngine,
    store: LocalCheckpointStore,
    plan: Mapping[str, Any],
    execution: Mapping[str, Any],
    *,
    expected_execution_hash: str | None = None,
) -> dict[str, Any]:
    """Deterministically replay store, plan, prefix admission, and continuation."""

    if not isinstance(execution, Mapping) or set(execution) != _EXECUTION_KEYS:
        raise ValueError("execution must contain exactly result and receipt")
    receipt = execution["receipt"]
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
        raise ValueError("execution receipt has unsupported fields")

    execution_hash = _require_sha256(
        receipt.get("executionHash"), "executionHash"
    )
    if expected_execution_hash is not None:
        pinned = _require_sha256(
            expected_execution_hash, "expected_execution_hash"
        )
        if execution_hash != pinned:
            raise ValueError("execution does not match caller-pinned identity")

    expected = execute_checkpoint_resume(
        engine,
        store,
        plan,
        expected_plan_hash=receipt.get("planHash"),
    )
    if dict(execution) != expected:
        raise ValueError("checkpoint resume execution failed deterministic replay")

    return {
        "schema": CHECKPOINT_RESUME_EXECUTION_VERIFICATION_SCHEMA,
        "valid": True,
        "executionHash": execution_hash,
        "planHash": receipt["planHash"],
        "checkpointHash": receipt["checkpointHash"],
        "resultReceiptHash": receipt["resultReceiptHash"],
        "resultStatus": receipt["resultStatus"],
        "resultCommitted": False,
        "resumeExecuted": True,
        "historyCommitted": False,
        "canonical": False,
    }
