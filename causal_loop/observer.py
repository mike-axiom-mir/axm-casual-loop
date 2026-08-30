from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .engine import deterministic_hash

OBSERVER_SCHEMA = "axm.causal-loop.observer-projection/v0.04"


def _frame(
    *,
    index: int,
    kind: str,
    wave: int | None,
    sources: list[str],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = deepcopy(dict(state))
    return {
        "index": index,
        "kind": kind,
        "wave": wave,
        "sources": list(sources),
        "state": snapshot,
        "stateHash": deterministic_hash(snapshot),
    }


def project_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Project an authoritative run receipt into read-only visual frames.

    The observer never executes causal modules or intervention handlers. It only applies
    writes that are already recorded in the receipt. Module writes from the same wave are
    grouped and applied atomically so the observer cannot invent intermediate canonical
    states that never existed in the engine.
    """

    source = deepcopy(dict(receipt))
    required = (
        "runId",
        "loopId",
        "receiptHash",
        "startState",
        "startStateHash",
        "stateTransitions",
        "endState",
        "endStateHash",
    )
    missing = [key for key in required if key not in source]
    if missing:
        raise ValueError("receipt missing observer fields: " + ",".join(sorted(missing)))

    state = deepcopy(dict(source["startState"]))
    if deterministic_hash(state) != source["startStateHash"]:
        raise ValueError("receipt start-state hash mismatch")

    frames: list[dict[str, Any]] = [
        _frame(index=0, kind="start", wave=None, sources=["START"], state=state)
    ]
    transitions = list(source["stateTransitions"])
    cursor = 0

    while cursor < len(transitions):
        transition = transitions[cursor]
        kind = transition.get("kind")

        if kind == "external":
            state.update(deepcopy(dict(transition.get("writes", {}))))
            computed = deterministic_hash(state)
            expected = transition.get("stateHash")
            if expected is not None and computed != expected:
                raise ValueError("external transition state hash mismatch")
            frames.append(
                _frame(
                    index=len(frames),
                    kind="external",
                    wave=transition.get("wave"),
                    sources=[str(transition.get("source", "external"))],
                    state=state,
                )
            )
            cursor += 1
            continue

        if kind == "module":
            wave = transition.get("wave")
            group: list[Mapping[str, Any]] = []
            while cursor < len(transitions):
                candidate = transitions[cursor]
                if candidate.get("kind") != "module" or candidate.get("wave") != wave:
                    break
                group.append(candidate)
                cursor += 1

            merged: dict[str, Any] = {}
            sources: list[str] = []
            expected_hashes: set[str] = set()
            for item in group:
                sources.append(str(item.get("source", "module")))
                if item.get("stateHash") is not None:
                    expected_hashes.add(str(item["stateHash"]))
                for key, value in dict(item.get("writes", {})).items():
                    if key in merged and merged[key] != value:
                        raise ValueError("observer found contradictory writes in one module wave")
                    merged[key] = deepcopy(value)

            if len(expected_hashes) > 1:
                raise ValueError("module wave contains inconsistent authoritative state hashes")
            state.update(merged)
            computed = deterministic_hash(state)
            if expected_hashes and computed != next(iter(expected_hashes)):
                raise ValueError("module wave state hash mismatch")
            frames.append(
                _frame(
                    index=len(frames),
                    kind="wave",
                    wave=wave,
                    sources=sources,
                    state=state,
                )
            )
            continue

        raise ValueError(f"unsupported transition kind for observer: {kind!r}")

    if deterministic_hash(state) != source["endStateHash"]:
        raise ValueError("observer projection does not reach receipt end-state hash")
    if state != source["endState"]:
        raise ValueError("observer projection does not reach receipt end state")

    projection = {
        "schema": OBSERVER_SCHEMA,
        "observerOnly": True,
        "authoritative": False,
        "runId": source["runId"],
        "loopId": source["loopId"],
        "authoritativeReceiptHash": source["receiptHash"],
        "startStateHash": source["startStateHash"],
        "endStateHash": source["endStateHash"],
        "frameCount": len(frames),
        "frames": frames,
    }
    projection["projectionHash"] = deterministic_hash(projection)
    return projection
