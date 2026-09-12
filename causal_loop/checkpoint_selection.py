from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .checkpoint_inventory import (
    checkpoint_candidate_projection,
    inspect_checkpoint_store,
)
from .checkpoint_store import LocalCheckpointStore
from .engine import deterministic_hash

CHECKPOINT_SELECTION_SCHEMA = "axm.causal-loop.checkpoint-selection/v0.01"
CHECKPOINT_RESUME_PLAN_SCHEMA = "axm.causal-loop.checkpoint-resume-plan/v0.01"
CHECKPOINT_RESUME_PLAN_VERIFICATION_SCHEMA = (
    "axm.causal-loop.checkpoint-resume-plan-verification/v0.01"
)
CHECKPOINT_RESUME_PLAN_AUTHORITY = (
    "EXPLICIT_SELECTION_ONLY_NO_AUTOMATIC_SELECTION_NO_RESUME_NO_CANON"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SELECTION_KEYS = {"schema", "candidateSetHash", "checkpointHash"}
_RECEIPT_KEYS = {
    "schema",
    "selection",
    "candidate",
    "authority",
    "planHash",
}


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _validate_selection(selection: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(selection, Mapping):
        raise TypeError("selection must be a mapping")
    if set(selection) != _SELECTION_KEYS:
        raise ValueError(
            "selection must contain exactly schema, candidateSetHash, and checkpointHash"
        )
    if selection["schema"] != CHECKPOINT_SELECTION_SCHEMA:
        raise ValueError("unsupported checkpoint selection schema")
    return {
        "schema": CHECKPOINT_SELECTION_SCHEMA,
        "candidateSetHash": _require_sha256(
            selection["candidateSetHash"], "candidateSetHash"
        ),
        "checkpointHash": _require_sha256(
            selection["checkpointHash"], "checkpointHash"
        ),
    }


def prepare_checkpoint_resume(
    store: LocalCheckpointStore, selection: Mapping[str, Any]
) -> dict[str, Any]:
    """Prepare evidence for one exact caller choice without resuming execution."""

    if not isinstance(store, LocalCheckpointStore):
        raise TypeError("store must be a LocalCheckpointStore")
    exact_selection = _validate_selection(selection)
    inventory = inspect_checkpoint_store(store)
    if inventory["candidateSetHash"] != exact_selection["candidateSetHash"]:
        raise ValueError("checkpoint candidate set changed since selection")

    selected = next(
        (
            candidate
            for candidate in inventory["candidates"]
            if candidate["checkpointHash"] == exact_selection["checkpointHash"]
        ),
        None,
    )
    if selected is None:
        raise ValueError("selected checkpoint is not a verified candidate")

    try:
        checkpoint = store.load(exact_selection["checkpointHash"])
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ValueError("selected checkpoint changed during selection") from exc
    if checkpoint_candidate_projection(checkpoint) != selected:
        raise ValueError("selected checkpoint changed during selection")

    receipt_body = {
        "schema": CHECKPOINT_RESUME_PLAN_SCHEMA,
        "selection": exact_selection,
        "candidate": deepcopy(selected),
        "authority": CHECKPOINT_RESUME_PLAN_AUTHORITY,
    }
    receipt = {**receipt_body, "planHash": deterministic_hash(receipt_body)}
    return {"checkpoint": deepcopy(checkpoint), "receipt": receipt}


def verify_checkpoint_resume_plan(
    store: LocalCheckpointStore,
    plan: Mapping[str, Any],
    expected_plan_hash: str | None = None,
) -> dict[str, Any]:
    """Replay a prepared plan against current store evidence without resuming it."""

    if not isinstance(store, LocalCheckpointStore):
        raise TypeError("store must be a LocalCheckpointStore")
    if not isinstance(plan, Mapping):
        raise TypeError("plan must be a mapping")
    if set(plan) != {"checkpoint", "receipt"}:
        raise ValueError("plan must contain exactly checkpoint and receipt")
    receipt = plan["receipt"]
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
        raise ValueError("plan receipt has unsupported fields")

    plan_hash = _require_sha256(receipt["planHash"], "planHash")
    if expected_plan_hash is not None:
        pinned = _require_sha256(expected_plan_hash, "expected_plan_hash")
        if plan_hash != pinned:
            raise ValueError("plan does not match caller-pinned identity")

    expected = prepare_checkpoint_resume(store, receipt["selection"])
    if dict(plan) != expected:
        raise ValueError("checkpoint resume plan failed deterministic replay")

    selection = expected["receipt"]["selection"]
    return {
        "schema": CHECKPOINT_RESUME_PLAN_VERIFICATION_SCHEMA,
        "valid": True,
        "planHash": plan_hash,
        "candidateSetHash": selection["candidateSetHash"],
        "checkpointHash": selection["checkpointHash"],
        "resumeExecuted": False,
        "canonical": False,
    }
