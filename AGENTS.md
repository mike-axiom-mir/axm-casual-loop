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
2. Claim one clearly named lane for this chat.
3. Make all implementation commits for that chat in the claimed lane.
4. Prefer one evolving PR from that lane instead of opening multiple parallel PRs.
5. Add follow-up fixes, tests, documentation, and review repairs to the same lane while the chat remains active.
6. Do not create side branches for convenience.
7. Do not spread one chat's work across unrelated PRs.
8. Do not take over another active chat/agent lane unless Mike explicitly asks for it.
9. If the current lane is blocked, report the blocker instead of silently spawning another lane.
10. A new chat may claim a new lane only after checking what already exists.

## 3. Source-honesty boundary

Keep observed, interpretation, proposal, and not-yet-proven claims separate. Evidence can move a claim upward only when tests or measurements support it.

## 4. v0.01 scope

Start with one deterministic train-platform loop with explicit invariants, modular deterministic event/rule units, shared state, bounded external intervention, deterministic merge, convergence, replay, hashes, run receipts, and headless execution. Keep AI/neural models out of v0.01.

## 5. Architecture boundaries

Preserve TruthGrid as canonical deterministic truth, Causal Loop Fabric as temporal/run structure, EchoWorld as committed history, and Ignition Fabric as later materialization. Presentation/rendering must not become authoritative state.

## 6. Deterministic module rule

Prefer small deterministic modules that read shared state and propose bounded writes/events. Do not encode giant special-case trees where smaller shared-state rules suffice.

## 7. External influence rule

Humans or machines inject direction/actions, not authoritative consequences. The fabric derives consequences from canonical state and deterministic rules.

## 8. Convergence rule

Every runnable loop defines how it ends or fails, with convergence conditions, bounded depth/event budget, contradiction/failure state, and recovery/restart policy.

## 9. Operational state vs lineage/history

Keep resettable operational loop state separate from persistent lineage/history state.

## 10. Required first-proof tests

Prove deterministic replay, invariant preservation, bounded cycles/convergence, independent-instance agreement, headless operation, and separation of operational state from history.

## 11. Receipts and evidence

Prefer evidence over narrative. Preserve failures and contradictions as data.

## 12. Metrics

Track enough correctness and cost metrics to evaluate active workset size, deterministic mismatches, convergence, resource use, and later experience quality.

## 13. Failure modes to keep visible

Surface state explosion, non-convergence, contradictory writes, hidden ordering dependence, over-fragmentation, railroading, incoherent free space, boring valid loops, unstable history, and unsupported AI-introduced rules.

## 14. Change discipline

Preserve active architecture, keep deterministic behavior inspectable, avoid hidden state/fallbacks/fake success, and use unknown/unverified/not-yet-tested honestly.

## 15. Merge discipline

A PR explains what changed, what stayed unchanged, tests, evidence, known gaps, and claim-boundary changes. Do not merge architectural claims merely because code compiles.

## 16. Direction sentence

**Fix the boundaries. Modularize the middle. Let shared state entangle consequences. Let humans or machines change direction. Then converge into a valid endpoint.**

## 17. Detail-density and composable capability principle

Quality is often the accumulated result of many small correct details, not one large generic upgrade.

- Look for missing small, bounded capabilities/checks/passes/repairs that control specific details or failure modes.
- Prefer reusable, inspectable, composable capabilities over one opaque "make it better" step when granularity creates real control or evidence.
- The machine remains useful without AI; AI primarily interprets goals and orchestrates underlying capabilities.
- Judge improvement by accumulated detail, coherence, failure reduction, and goal fit—not just model size, resolution, benchmark score, or one broad upgrade.
- Do not fragment working systems merely for ideology.

**Working rule:** thousands of small good details and capabilities in the right places can improve a result more than one simple big upgrade.

## 18. Canonical state and adaptive realization principle

When useful, separate **what exists** from **how it is expressed on a particular machine**.

- Canonical state/identity is authoritative; render/UI/audio/device realizations are replaceable expressions unless explicitly defined otherwise.
- Preserve expression intent separately where needed: meaning, material character, motion weight, readability, atmosphere, hierarchy, sound intent, and semantic detail.
- Prefer one truthful body with multiple realization contracts over divergent `mobile`, `lite`, `desktop`, `ultra`, or platform editions when the same canonical state can support them.
- Choose realization from canonical state + expression intent + measured machine capabilities + user policy; adaptation may happen at launch or dynamically.
- A weak device should usually receive a cheaper expression, **not weaker truth**.
- Define non-degradable invariants explicitly: rules, fairness, data integrity, core functionality, privacy, causal/timing meaning, content identity, and authoritative state as applicable.
- Never let a lossy realization overwrite richer canonical state. A projection/cache is not authority.
- Upgrading expression must not invent canonical facts; downgrading expression must not erase them.
- Build bounded alternative realization paths where useful: geometry, textures, lighting, particles, simulation passes, UI density, preview fidelity, audio richness, or domain equivalents.
- Do not force the split where representation itself is canonical truth.

**Working rule:** degrade expression, never truth; upgrade expression, never invent truth. One body may wake up differently on different machines while remaining the same thing.
