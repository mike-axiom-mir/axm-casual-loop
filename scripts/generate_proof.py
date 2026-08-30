from __future__ import annotations

import json
from pathlib import Path

from causal_loop.train_platform import build_engine, initial_state

SCENARIOS = {
    "no_intervention": ["WAIT"],
    "block_door": ["BLOCK_DOOR"],
    "trigger_alarm": ["TRIGGER_ALARM"],
    "block_plus_alarm": ["BLOCK_DOOR", "TRIGGER_ALARM"],
}


def build_proof() -> dict:
    engine = build_engine()
    proof = {
        "schema": "axm.causal-loop.v0.01-proof/v1",
        "scenarios": {},
    }
    for name, actions in SCENARIOS.items():
        receipt = engine.run(initial_state(), actions)
        proof["scenarios"][name] = {
            "orderedExternalInfluences": actions,
            "status": receipt["status"],
            "runId": receipt["runId"],
            "endStateHash": receipt["endStateHash"],
            "receiptHash": receipt["receiptHash"],
            "departureDelay": receipt["endState"]["train.departureDelay"],
            "modulesActivated": receipt["modulesActivated"],
            "hardEndPassed": next(
                result["passed"]
                for result in receipt["invariantResults"]
                if result["kind"] == "hard_end"
            ),
            "softOnTimePassed": next(
                result["passed"]
                for result in receipt["invariantResults"]
                if result["id"] == "on_time_departure"
            ),
            "contradictionCount": len(receipt["contradictions"]),
        }

    first = engine.run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
    second = engine.run(initial_state(), ["BLOCK_DOOR", "TRIGGER_ALARM"])
    proof["repeatability"] = {
        "sameReceiptHash": first["receiptHash"] == second["receiptHash"],
        "sameEndStateHash": first["endStateHash"] == second["endStateHash"],
        "sameStateTransitions": first["stateTransitions"] == second["stateTransitions"],
    }
    proof["localTestCommand"] = "python -m unittest discover -s tests -v"
    return proof


def main() -> None:
    output = Path("evidence/v0.01-proof.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_proof(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
