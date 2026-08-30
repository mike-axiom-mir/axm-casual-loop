from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.engine import TimedInfluence
from causal_loop.train_platform import build_engine, initial_state

LEGACY_SCENARIOS = {
    "no_intervention": ["WAIT"],
    "block_door": ["BLOCK_DOOR"],
    "trigger_alarm": ["TRIGGER_ALARM"],
    "block_plus_alarm": ["BLOCK_DOOR", "TRIGGER_ALARM"],
}

TIMED_SCENARIOS = {
    "block_while_door_open": [TimedInfluence(2, "BLOCK_DOOR")],
    "block_after_door_closed": [TimedInfluence(4, "BLOCK_DOOR")],
    "alarm_mid_run": [TimedInfluence(2, "TRIGGER_ALARM")],
    "block_then_alarm": [TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(3, "TRIGGER_ALARM")],
    "future_alarm_after_convergence": [TimedInfluence(9, "TRIGGER_ALARM")],
}


def summarize(receipt: dict) -> dict:
    return {
        "status": receipt["status"],
        "runId": receipt["runId"],
        "endStateHash": receipt["endStateHash"],
        "receiptHash": receipt["receiptHash"],
        "departureDelay": receipt["endState"]["train.departureDelay"],
        "modulesActivated": receipt["modulesActivated"],
        "timedExternalInfluences": receipt["timedExternalInfluences"],
        "appliedTimedInfluences": receipt["appliedTimedInfluences"],
        "unappliedTimedInfluences": receipt["unappliedTimedInfluences"],
        "hardEndPassed": next(
            result["passed"] for result in receipt["invariantResults"] if result["kind"] == "hard_end"
        ),
        "softOnTimePassed": next(
            result["passed"] for result in receipt["invariantResults"] if result["id"] == "on_time_departure"
        ),
        "contradictionCount": len(receipt["contradictions"]),
    }


def build_proof() -> dict:
    engine = build_engine()
    proof = {
        "schema": "axm.causal-loop.v0.02-timed-proof/v1",
        "legacyScenarios": {},
        "timedScenarios": {},
    }

    for name, actions in LEGACY_SCENARIOS.items():
        proof["legacyScenarios"][name] = summarize(engine.run(initial_state(), actions))

    for name, schedule in TIMED_SCENARIOS.items():
        proof["timedScenarios"][name] = summarize(
            engine.run(initial_state(), timed_influences=schedule)
        )

    schedule = [TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(3, "TRIGGER_ALARM")]
    first = engine.run(initial_state(), timed_influences=schedule)
    second = engine.run(initial_state(), timed_influences=schedule)
    replay = engine.replay(first)
    proof["timedRepeatability"] = {
        "sameReceiptHash": first["receiptHash"] == second["receiptHash"],
        "sameEndStateHash": first["endStateHash"] == second["endStateHash"],
        "sameStateTransitions": first["stateTransitions"] == second["stateTransitions"],
        "replayMatches": replay["replayMatches"],
    }
    proof["timingChangesConsequence"] = {
        "sameAction": "BLOCK_DOOR",
        "whileDoorOpenWave": 2,
        "whileDoorOpenDelay": proof["timedScenarios"]["block_while_door_open"]["departureDelay"],
        "afterDoorClosedWave": 4,
        "afterDoorClosedDelay": proof["timedScenarios"]["block_after_door_closed"]["departureDelay"],
        "differentEndStateHash": (
            proof["timedScenarios"]["block_while_door_open"]["endStateHash"]
            != proof["timedScenarios"]["block_after_door_closed"]["endStateHash"]
        ),
    }
    proof["localTestCommand"] = "python -m unittest discover -s tests -v"
    return proof


def main() -> None:
    output = ROOT / "evidence" / "v0.02-timed-proof.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_proof(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
