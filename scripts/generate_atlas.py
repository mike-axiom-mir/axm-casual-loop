from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.explorer import bounded_schedule_cases, explore_schedule_space
from causal_loop.train_platform import build_engine, initial_state

ACTIONS = ("BLOCK_DOOR", "TRIGGER_ALARM", "TALK_TO_PASSENGER")
WAVES = range(6)


def build_atlas() -> dict:
    cases = bounded_schedule_cases(ACTIONS, WAVES)
    return explore_schedule_space(build_engine(), initial_state(), cases)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the bounded AXM Causal Loop Atlas.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    atlas = build_atlas()
    text = json.dumps(atlas, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": atlas["summary"], "atlasHash": atlas["atlasHash"]}, sort_keys=True))


if __name__ == "__main__":
    main()
