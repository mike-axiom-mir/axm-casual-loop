# AXM Causal Loop Fabric

A source-honest prototype for testing whether a bounded deterministic loop can keep fixed structural boundaries while small shared-state modules produce different valid causal interiors under different external interventions.

## Status

**v0.01 proof harness. Not a game engine, movie engine, VR engine, or general simulation claim.**

The current prototype is one headless `TRAIN PLATFORM LOOP`:

- start invariant: train approaches the station
- hard end invariant: train eventually leaves
- external direction: `WAIT`, `BLOCK_DOOR`, `TRIGGER_ALARM`, `TALK_TO_PASSENGER`
- consequences are derived by deterministic modules, not declared by the actor
- all module writes merge deterministically
- run receipts include hashes, transitions, activated modules, contradictions, invariant results, and resource work units
- replay reconstructs the same causal run from start state + ordered influences
- persistent history only accepts explicitly committed converged runs

## Run the proof

Requires Python 3.11+ and no third-party packages.

```bash
python -m unittest discover -s tests -v
```

## Tiny example

```python
from causal_loop.train_platform import build_engine, initial_state

engine = build_engine()
receipt = engine.run(initial_state(), ["BLOCK_DOOR"], commit=True)

print(receipt["status"])
print(receipt["modulesActivated"])
print(receipt["endStateHash"])
```

## Claim boundary

What this repository may prove at v0.01 is intentionally narrow: the same bounded loop can deterministically replay the same ordered inputs, while different external direction can activate a different valid causal path that still converges.

It does **not** yet prove large loop spaces are cheap, that automatically created loops are compelling, that arbitrary software/media can be compiled into this form, or that this architecture outperforms established engines.

See `AGENTS.md` for collaboration, source-honesty, and one-lane-per-chat rules.
