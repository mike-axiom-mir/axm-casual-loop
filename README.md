# AXM Causal Loop Fabric

A source-honest prototype for testing whether a bounded deterministic loop can keep fixed structural boundaries while small shared-state modules produce different valid causal interiors under external intervention.

## Status

**v0.03 checkpoint/resume proof harness. Not a game engine, movie engine, VR engine, or general simulation claim.**

The current prototype is one headless `TRAIN PLATFORM LOOP` with:

- start invariant: train approaches the station
- hard end invariant: train eventually leaves
- external direction: `WAIT`, `BLOCK_DOOR`, `TRIGGER_ALARM`, `TALK_TO_PASSENGER`
- consequences derived by deterministic modules, not declared by the actor
- atomic deterministic module merge from one frozen wave snapshot
- timed interventions that enter before explicit causal waves
- exact run receipts with hashes, transitions, activated modules, contradictions, invariants, and resource work units
- deterministic replay from the same start state + timed intervention sequence
- explicit distinction between scheduled, applied, and never-reached interventions
- deterministic checkpointing between causal waves
- checkpoint hash + state hash + engine-signature validation before resume
- resume that continues the already-executed causal prefix rather than replaying it
- persistent history accepting only explicitly committed converged runs

## v0.02: timing becomes causal input

```text
same start + BLOCK_DOOR at wave 2 -> door open -> obstruction -> delay 1
same start + BLOCK_DOOR at wave 4 -> door already closed -> no retroactive obstruction -> delay 0
```

The actor still injects only direction (`BLOCK_DOOR`). Canonical state decides the consequence.

## v0.03: pause and resume

A run can now stop exactly between deterministic causal waves:

```text
start
 -> wave 0
 -> wave 1
 -> CHECKPOINT
 -> resume at wave 2
 -> timed intervention
 -> causal consequences
 -> convergence
```

The proof requires the resumed run to equal an uninterrupted run for:

- run ID
- final receipt hash
- end-state hash
- ordered state transitions
- convergence path

Checkpoint state is hash-protected. Altering checkpoint state without recomputing a valid checkpoint is rejected.

## Run the proof

Requires Python 3.11+ and no third-party packages.

```bash
python -m unittest discover -s tests -v
python scripts/generate_proof.py
git diff --exit-code -- evidence/v0.03-checkpoint-proof.json
```

Current local suite: **25 tests**.

## Tiny example

```python
from causal_loop.engine import TimedInfluence
from causal_loop.train_platform import build_engine, initial_state

engine = build_engine()
schedule = [TimedInfluence(2, "BLOCK_DOOR")]

checkpoint = engine.pause(
    initial_state(),
    timed_influences=schedule,
    after_waves=2,
)

receipt = engine.resume(checkpoint)
```

## Claim boundary

The current proof is intentionally narrow. It supports the claim that a bounded deterministic scene can replay identical timed external input, pause at a deterministic causal boundary, and continue from a hash-validated checkpoint to the same canonical result as uninterrupted execution.

It does **not** yet prove large loop spaces are cheap, arbitrary wall-clock concurrency is deterministic, automatically created loops are compelling, arbitrary software/media can be compiled into this form, or that this architecture outperforms established engines.

The next sensible proof is a tiny visual observer over the authoritative causal state, followed by a larger scene only after the observer remains non-authoritative.

See `AGENTS.md` for collaboration, source-honesty, and one-lane-per-chat rules.
