from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.atlas_verifier import verify_atlas


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a saved AXM Causal Loop Atlas before evidence admission."
    )
    parser.add_argument("atlas", type=Path)
    parser.add_argument("--engine-signature", default=None)
    parser.add_argument("--loop-id", default=None)
    parser.add_argument("--loop-version", default=None)
    args = parser.parse_args()

    try:
        payload = json.loads(args.atlas.read_text(encoding="utf-8"))
        receipt = verify_atlas(
            payload,
            expected_engine_signature=args.engine_signature,
            expected_loop_id=args.loop_id,
            expected_loop_version=args.loop_version,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema": "axm.causal-loop.causal-atlas-verification/v0.01",
                    "accepted": False,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
