from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.engine import TimedInfluence
from causal_loop.train_platform import build_engine, initial_state


def build_demo_receipt() -> dict:
    return build_engine().run(
        initial_state(),
        timed_influences=[
            TimedInfluence(2, "BLOCK_DOOR"),
            TimedInfluence(3, "TRIGGER_ALARM"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a deterministic train-platform receipt for the read-only observer.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "observer" / "demo-receipt.json"),
        help="Output JSON path (default: observer/demo-receipt.json)",
    )
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = build_demo_receipt()
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
