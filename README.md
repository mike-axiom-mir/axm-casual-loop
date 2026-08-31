# AXM Causal Loop Fabric

A source-honest prototype for testing whether a bounded deterministic loop can keep fixed structural boundaries while small shared-state modules produce different valid causal interiors under external intervention.

## Status

**v0.10 deterministic-contract proof harness. Not a game engine, movie engine, VR engine, or general simulation claim.**

The current prototype is one deterministic `TRAIN PLATFORM LOOP`. Its hard boundary is simple: the train approaches, causal events unfold, and the train eventually leaves. The interior can change through timed external direction while canonical consequences remain derived by deterministic modules.

Current capabilities:

- atomic module waves from one frozen state snapshot
- timed external interventions with scheduled/applied/unapplied receipt separation
- deterministic hashes and exact replay
- cycle, contradiction, event-budget, and explicit convergence failures
- deterministic pause/checkpoint/resume without replaying the completed prefix
- commit-gated persistent history
- a self-contained local receipt observer with no causal authority or network dependency
- bounded Causal Atlas exploration across single, paired, reversed-same-wave, and repeated actions
- enforced `Module.authority_scope` for canonical writes
- enforced `Module.reads` for predicate and transition state access
- enforced `LoopSpec.intervention_write_scope` so outside actors can inject direction but cannot declare authoritative consequences
- enforced `Module.dependencies` using the current `all-prior-activation/v0.01` policy

## Current remote proof

GitHub Actions currently verifies:

- **64/64 tests passing**
- **208/208 bounded Atlas schedules converging**
- **183 unique realized causal paths**
- **9 unique endpoint states**
- 0 deterministic mismatches
- 0 contradictions
- 0 hard-invariant failures
- 0 module authority violations in the train scene
- 0 undeclared module-read violations in the train scene
- 0 orphan external writes
- 0 unresolved external writes

Current Atlas hash:

```text
4a801858b301fa9918b2a741ef9c7937c70de91235aaa513c8911fc2d01ab707
```

## Direction is not consequence authority

External actors may request bounded direction such as:

```text
BLOCK_DOOR
TRIGGER_ALARM
TALK_TO_PASSENGER
```

The intervention boundary only permits the corresponding direction-state keys. It cannot directly write consequences such as train delay or departure state. Causal modules must derive those consequences from canonical state.

A rejected external consequence write fails explicitly with `intervention_scope_violation` before canonical state changes.

## Dependencies are now causal

Earlier versions signed `Module.dependencies` into module contracts but did not enforce them. The red detection evidence is preserved in `evidence/v0.10-dependency-gap.json`, and the pre-enforcement executor is preserved as `causal_loop/engine_v06.py`.

The current dependency policy means:

```text
registered prerequisite
+ prerequisite actually activated in an earlier committed wave
= dependency satisfied
```

The executor now rejects missing dependency IDs, self-dependencies, duplicate dependency declarations, and dependency cycles. Same-wave module order cannot satisfy a dependency. If a module is causally relevant but blocked by a prerequisite that cannot be satisfied, the run fails explicitly with `unsatisfied_dependencies` and records deterministic dependency-block evidence.

The train scene only declares dependencies where the relationship is genuinely required. Optional or OR-shaped relationships are not forced into an inaccurate AND dependency graph.

## Timing becomes causal input

```text
same start + BLOCK_DOOR at wave 2 -> door open -> obstruction -> delay 1
same start + BLOCK_DOOR at wave 4 -> door already closed -> no retroactive obstruction -> delay 0
```

Same start state plus the same ordered timed inputs reproduces the same deterministic receipt.

## Pause and resume

A run can stop exactly between causal waves:

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

Checkpoint state, run identity, loop identity, engine signature, and dependency policy are validated before continuation.

## Observer glass, not a second engine

`observer/index.html` is a self-contained local viewer for completed causal receipts. It can play, pause, step, and scrub the recorded scene, but it cannot execute modules, inject actions, resolve contradictions, write canonical state, or reach the internet.

Rendering remains presentation. The receipt remains evidence.

## Run the proof

Requires Python 3.11+ and no third-party packages.

```bash
python -m unittest discover -s tests -v
python scripts/export_demo_receipt.py
python scripts/generate_atlas.py --output /tmp/axm-causal-atlas.json
```

Open `observer/index.html` locally and load the generated demo receipt to inspect a run visually.

## Evidence trail

The repo intentionally preserves useful red states instead of rewriting history. Detection and repair evidence includes timing, causal debt, repeated incidents, module write authority, module read contracts, external intervention authority, and dependency enforcement.

The latest dependency repair summary is `evidence/v0.10-dependency-repair.json`.

## Claim boundary

The proof remains deliberately narrow. It supports the claim that this bounded deterministic scene can vary its causal interior under timed direction while replay, checkpoints, presentation boundaries, declared read/write authority, external direction scope, and a simple prior-activation dependency contract remain explicit and testable.

It does **not** prove that large loop spaces are cheap, that arbitrary wall-clock concurrency is deterministic, that arbitrary games/movies/VR can be compiled into this form, that automatic generation will be compelling, or that this architecture outperforms established engines.

The current dependency policy is specifically an AND-of-prior-module-activation contract. Optional, OR, quorum, state-only, or richer causal relationships need their own explicit semantics rather than being squeezed into `Module.dependencies`.

See `AGENTS.md` for collaboration, source-honesty, and one-lane-per-chat rules.
