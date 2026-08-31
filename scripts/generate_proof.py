from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.engine import TimedInfluence
from causal_loop.train_platform import build_engine, initial_state


def build_proof() -> dict:
    engine = build_engine()

    wave2 = engine.run(initial_state(), timed_influences=[TimedInfluence(2, "BLOCK_DOOR")])
    wave4 = engine.run(initial_state(), timed_influences=[TimedInfluence(4, "BLOCK_DOOR")])

    schedule = [TimedInfluence(2, "BLOCK_DOOR"), TimedInfluence(3, "TRIGGER_ALARM")]
    uninterrupted = engine.run(initial_state(), timed_influences=schedule)
    checkpoint = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)
    resumed = engine.resume(checkpoint)
    repeated_checkpoint = engine.pause(initial_state(), timed_influences=schedule, after_waves=2)

    return {
        "schema": "axm.causal-loop.v0.03-checkpoint-proof/v1",
        "timedBaseline": {
            "sameAction": "BLOCK_DOOR",
            "wave2Delay": wave2["endState"]["train.departureDelay"],
            "wave4Delay": wave4["endState"]["train.departureDelay"],
            "differentEndStateHash": wave2["endStateHash"] != wave4["endStateHash"],
        },
        "checkpoint": {
            "afterWaves": checkpoint["wavesExecuted"],
            "checkpointHash": checkpoint["checkpointHash"],
            "stateHash": checkpoint["stateHash"],
            "appliedTimedInfluencesBeforePause": checkpoint["appliedTimedInfluences"],
            "sameCheckpointHashOnRepeat": checkpoint["checkpointHash"] == repeated_checkpoint["checkpointHash"],
        },
        "resumeEquivalence": {
            "sameRunId": resumed["runId"] == uninterrupted["runId"],
            "sameReceiptHash": resumed["receiptHash"] == uninterrupted["receiptHash"],
            "sameEndStateHash": resumed["endStateHash"] == uninterrupted["endStateHash"],
            "sameStateTransitions": resumed["stateTransitions"] == uninterrupted["stateTransitions"],
            "sameConvergencePath": resumed["convergencePath"] == uninterrupted["convergencePath"],
            "status": resumed["status"],
            "departureDelay": resumed["endState"]["train.departureDelay"],
        },
        "testCommand": "python -m unittest discover -s tests -v",
        "testCount": 30,
    }


def main() -> None:
    output = ROOT / "evidence" / "v0.03-checkpoint-proof.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_proof(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
