from __future__ import annotations

import re
from typing import Any

from .checkpoint_store import LocalCheckpointStore
from .engine import deterministic_hash

CHECKPOINT_INVENTORY_SCHEMA = "axm.causal-loop.checkpoint-inventory/v0.01"
CHECKPOINT_INVENTORY_AUTHORITY = (
    "DERIVED_DISCOVERY_ONLY_NO_SELECTION_NO_RESUME_NO_CANON"
)
_FINAL_NAME = re.compile(r"^(?P<checkpoint>[0-9a-f]{64})\.json$")
_TEMP_NAME = re.compile(r"^\.[0-9a-f]{64}\..+\.tmp$")


def _candidate_projection(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "checkpointHash": checkpoint["checkpointHash"],
        "checkpointSchema": checkpoint.get("schema"),
        "loopId": checkpoint.get("loopId"),
        "loopVersion": checkpoint.get("loopVersion"),
        "runId": checkpoint.get("runId"),
        "engineSignature": checkpoint.get("engineSignature"),
        "startStateHash": checkpoint.get("startStateHash"),
        "stateHash": checkpoint.get("stateHash"),
        "wavesExecuted": checkpoint.get("wavesExecuted"),
        "maxWaves": checkpoint.get("maxWaves"),
    }


def inspect_checkpoint_store(store: LocalCheckpointStore) -> dict[str, Any]:
    """Reconstruct a non-authoritative checkpoint inventory from final store bytes.

    This is deliberately not a ``latest`` pointer and does not select or resume a
    checkpoint. Every candidate is reloaded through ``LocalCheckpointStore.load()``,
    so only exact canonical content-addressed checkpoint bytes enter the candidate
    set. Invalid final identities are reported as held evidence instead of blocking
    discovery of independent valid checkpoints.
    """

    if not isinstance(store, LocalCheckpointStore):
        raise TypeError("store must be a LocalCheckpointStore")

    candidates: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    abandoned_temp_count = 0
    ignored_entry_count = 0

    for entry in sorted(store.root.iterdir(), key=lambda item: item.name):
        match = _FINAL_NAME.fullmatch(entry.name)
        if match:
            checkpoint_id = match.group("checkpoint")
            try:
                checkpoint = store.load(checkpoint_id)
            except FileNotFoundError:
                held.append(
                    {
                        "checkpointHash": checkpoint_id,
                        "reason": "FILE_DISAPPEARED_DURING_SCAN",
                    }
                )
            except ValueError:
                held.append(
                    {
                        "checkpointHash": checkpoint_id,
                        "reason": "CHECKPOINT_ADMISSION_FAILED",
                    }
                )
            except OSError:
                held.append(
                    {
                        "checkpointHash": checkpoint_id,
                        "reason": "CHECKPOINT_READ_FAILED",
                    }
                )
            else:
                candidates.append(_candidate_projection(checkpoint))
            continue

        if _TEMP_NAME.fullmatch(entry.name):
            abandoned_temp_count += 1
        else:
            ignored_entry_count += 1

    candidates.sort(key=lambda item: item["checkpointHash"])
    held.sort(key=lambda item: item["checkpointHash"])

    candidate_identity = {
        "schema": CHECKPOINT_INVENTORY_SCHEMA,
        "candidates": candidates,
    }
    return {
        "schema": CHECKPOINT_INVENTORY_SCHEMA,
        "candidateSetHash": deterministic_hash(candidate_identity),
        "candidateCount": len(candidates),
        "heldCount": len(held),
        "candidates": candidates,
        "held": held,
        "diagnostics": {
            "abandonedTempCount": abandoned_temp_count,
            "ignoredEntryCount": ignored_entry_count,
        },
        "authority": CHECKPOINT_INVENTORY_AUTHORITY,
    }
