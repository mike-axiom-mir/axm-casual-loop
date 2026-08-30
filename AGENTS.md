# AXM Causal Loop Fabric — Agent Rules

Status: repository bootstrap guardrail
Applies to: all human + AI contributors, coding agents, research agents, reviewers, and automated builders

## 1. Core direction

This repository exists to test and build the AXM Causal Loop Fabric as a source-honest deterministic architecture.

Current safe claim:

> It is technically plausible to build a deterministic modular scene/process whose start/end constraints remain bounded while external influence changes the causal path through small shared-state modules.

Do not silently promote proposals into verified facts.

The initial target is deliberately small: build and prove one deterministic train-platform causal loop before attempting a full game, movie, VR world, or general creation system.

## 2. One lane per chat / agent instance

**Hard collaboration rule: one active implementation lane per chat or agent instance.**

A chat/agent that begins implementation work must claim one branch / PR lane and remain inside it for the lifetime of that chat unless Mike explicitly redirects it.

### Required behavior

1. Inspect existing branches and open PRs before creating a new implementation lane.
2. Claim one clearly named lane for this chat, for example:
   - `chat/causal-loop-v0.01-lane-1`
   - `codex/causal-loop-v0.01-lane-2`
3. Make all implementation commits for that chat in the claimed lane.
4. Prefer one evolving PR from that lane instead of opening multiple parallel PRs.
5. Add follow-up fixes, tests, documentation, and review repairs to the same lane while the chat remains active.
6. Do not create side branches for convenience.
7. Do not spread one chat's work across unrelated PRs.
8. Do not take over another active chat/agent lane unless Mike explicitly asks for it.
9. If the current lane is blocked, report the blocker instead of silently spawning another lane.
10. A new chat may claim a new lane only after checking what already exists.

### Why this rule exists

AXM work can branch faster than it can be reviewed. One lane per chat keeps provenance visible, prevents duplicate work, reduces merge collisions, and makes it possible to understand which reasoning instance produced which implementation lineage.

## 3. Source-honesty boundary

Keep these categories separate in code, docs, tests, PR descriptions, and reports:

### Observed
- Small deterministic modules/state machines are normal software.
- Games already use events, state, loops, rules, and branching.
- Deterministic systems can react differently when their inputs or state differ.

### Interpretation
- Sufficiently modular deterministic events may form a larger runnable scene whose path changes through shared state.

### Proposal
- Build a reusable AXM fabric with explicit invariants, entangled/shared state, causal modules, intervention points, convergence rules, and receipts.

### Not yet proven
Do not claim as established:
- compelling interactive movies,
- cheap very-large loop spaces,
- arbitrary creations compiled automatically into causal loops,
- safe generic AI extension of loops,
- superiority over ordinary game/narrative engines,
- infinite or limitless simulation,
- automatically fun content,
- production-ready VR capability.

Evidence can move an item upward only when tests or measurements actually support it.

## 4. v0.01 scope

Do not begin with a giant world.

Build one deterministic `TRAIN PLATFORM LOOP` with:
- explicit start invariant,
- explicit hard end invariant,
- small modular deterministic event/rule units,
- shared state,
- bounded external intervention,
- deterministic merge,
- convergence,
- replay,
- hashes,
- run receipts,
- headless execution.

Keep AI and neural models out of v0.01.

No generated assets are required for the first proof.

## 5. Architecture boundaries

Preserve these responsibilities if/when connected to the wider AXM stack:

- **TruthGrid** decides canonical deterministic truth.
- **Causal Loop Fabric** decides temporal/run structure, module activation, invariants, interventions, and convergence.
- **EchoWorld** remembers committed history.
- **Ignition Fabric** may later materialize only the currently relevant workset/modules.

Do not let EchoWorld record an uncommitted causal event.

Do not let presentation/rendering become the authoritative state. The authoritative object is causal state + committed history.

## 6. Deterministic module rule

Prefer small deterministic modules that read shared state and propose bounded writes/events.

A module should have an explicit contract covering, as appropriate:
- identity/version,
- reads,
- predicates,
- inputs,
- proposed writes,
- emitted events,
- authority scope,
- dependencies,
- convergence effects,
- determinism declaration,
- receipt schema.

Do not make every module a persistent agent by default.

Do not encode giant special-case branch trees when the same consequence can emerge from smaller shared-state rules.

## 7. External influence rule

Humans or machines inject **direction/actions**, not authoritative consequences.

Good:
- `BLOCK_DOOR`
- `MOVE`
- `OPEN`
- `SPEAK`
- `WAIT`

Bad:
- `SET_TRAIN_DELAYED_TRUE` when delay should be derived by the causal system.

The fabric determines consequences from canonical state and deterministic rules.

## 8. Convergence rule

Every runnable loop must define how it ends or fails.

Each loop should have:
- convergence conditions,
- maximum causal depth and/or event budget,
- explicit failure state,
- contradiction state,
- recovery/restart policy.

Never hide infinite churn behind timeouts without a receipt explaining what happened.

## 9. Operational state vs lineage/history

Do not assume loop reset means world-history reset.

Keep separate:
- operational loop state that may converge/reset,
- lineage/history state that may persist.

A repeating scene may return operationally to a valid starting structure while committed consequences remain in history.

## 10. Required first-proof tests

Before v0.01 is considered proven, tests should cover at least:

1. Same start + same ordered inputs = same end hash.
2. Different external influence can produce a different valid path.
3. Hard invariants still hold.
4. Soft invariants can be displaced.
5. Irrelevant modules do not execute.
6. Module completion order does not change the canonical result.
7. Causal cycles are detected and bounded.
8. Convergence failure produces an explicit failure receipt.
9. Replay reconstructs the exact run.
10. History can persist separately from operational loop state.
11. Uncommitted events cannot enter persistent memory.
12. The loop can run headless without rendering.

## 11. Receipts and evidence

Prefer evidence over narrative.

A useful run receipt should make visible, as appropriate:
- run ID and loop ID,
- start/end state hashes,
- ordered external influences,
- activated modules,
- state transitions,
- contradictions,
- convergence path,
- invariant results,
- history effects,
- resource usage.

Failures and contradictions are data. Do not erase them to make a run look successful.

## 12. Metrics

Record enough to evaluate both correctness and cost, including when practical:
- modules available,
- modules activated,
- state-transition count,
- causal depth,
- external influences,
- convergence steps,
- CPU time,
- active workset size,
- replay time,
- deterministic hash mismatches,
- invariant failures,
- soft-invariant deviations,
- contradiction count.

Later metrics may include distinct valid runs, memory growth, network cost, Ignition materialization savings, and human-rated experience quality.

## 13. Failure modes to keep visible

Actively watch for:
- state explosion,
- non-converging causal loops,
- modules repeatedly waking each other,
- contradictory writes,
- hidden ordering dependence,
- merge overhead from over-fragmentation,
- railroading caused by overly strict invariants,
- incoherent free space,
- valid-but-boring generated loops,
- unstable history accumulation,
- unsupported causal rules introduced by later AI systems.

Do not bury these behind abstractions. Surface them in tests, receipts, issues, or PR notes.

## 14. Change discipline

- Preserve the active architecture unless a change explicitly improves or repairs it.
- Do not rebuild from scratch merely because a different architecture is familiar.
- Keep deterministic behavior testable and inspectable.
- Avoid hidden global state.
- Avoid silent fallback behavior that changes semantics.
- Avoid fake success states.
- Never report work as complete until the repository state and tests support that claim.
- When evidence is missing, say `unknown`, `unverified`, or `not yet tested`.

## 15. Merge discipline

A PR should explain:
- what changed,
- what stayed deliberately unchanged,
- tests run,
- deterministic evidence produced,
- known failures/gaps,
- whether any claim boundary changed.

Do not merge architectural claims merely because code compiles.

## 16. Direction sentence

**Fix the boundaries. Modularize the middle. Let shared state entangle consequences. Let humans or machines change direction. Then converge into a valid endpoint.**
