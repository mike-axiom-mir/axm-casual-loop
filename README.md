# AXM Causal Loop Fabric

A source-honest prototype for testing whether a bounded deterministic loop can keep fixed structural boundaries while small shared-state modules produce different valid causal interiors under external intervention.

## Status

**v0.02 timed-intervention proof harness. Not a game engine, movie engine, VR engine, or general simulation claim.**

The current prototype is one headless `TRAIN PLATFORM LOOP` with:

- start invariant: train approaches the station
- hard end invariant: train eventually leaves
- external direction: `WAIT`, `BLOCK_DOOR`, `TRIGGER_ALARM`, `TALK_TO_PASSENGER`
- consequences derived by deterministic modules, not declared by the actor
- atomic deterministic module merge from one frozen wave snapshot
- exact run receipts with state hashes, transitions, activated modules, contradictions, invariants, and resource work units
- timed interventions that enter before an explicit causal wave
- replay from the same start state + same timed intervention sequence
- explicit distinction between scheduled, applied, and never-reached future interventions
- persistent history accepting only explicitly committed converged runs

## What v0.02 adds

Timing is now part of causal input.

```text
same start + BLOCK_DOOR at wave 2 -> door is open -> obstruction -> delay 1
same start + BLOCK_DOOR at wave 4 -> door already closed -> no retroactive obstruction -> delay 0
```

The actor still injects only direction (`BLOCK_DOOR`). The causal state decides the consequence.

## Run the proof

Requires Python 3.11+ and no third-party packages.

```bash
python -m unittest discover -s tests -v
python scripts/generate_proof.py
git diff --exit-code -- evidence/v0.02-timed-proof.json
```

## Tiny examples

Legacy pre-run direction remains supported:

```python
from causal_loop.train_platform import build_engine, initial_state

receipt = build_engine().run(initial_state(), ["BLOCK_DOOR"], commit=True)
```

Timed direction:

```python
from causal_loop.engine import TimedInfluence
from causal_loop.train_platform import build_engine, initial_state

receipt = build_engine().run(
    initial_state(),
    timed_influences=[TimedInfluence(2, "BLOCK_DOOR")],
)
```

## Claim boundary

The current proof is intentionally narrow. It supports the claim that a bounded deterministic scene can replay identical timed external inputs exactly, while the same external action at different causal moments can produce different valid consequences without rewriting prior state.

It does **not** yet prove large loop spaces are cheap, that automatically created loops are compelling, that arbitrary software/media can be compiled into this form, that arbitrary wall-clock concurrency is deterministic, or that this architecture outperforms established engines.

The next planned proof is deterministic checkpoint/pause/resume.

See `AGENTS.md` for collaboration, source-honesty, and one-lane-per-chat rules.
