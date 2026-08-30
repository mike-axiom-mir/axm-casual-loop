from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, Sequence

State = dict[str, Any]
Predicate = Callable[[Mapping[str, Any]], bool]
Transition = Callable[[Mapping[str, Any]], Mapping[str, Any]]
InterventionHandler = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def deterministic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Module:
    module_id: str
    version: str
    reads: tuple[str, ...]
    predicate: Predicate = field(compare=False, repr=False)
    transition: Transition = field(compare=False, repr=False)
    authority_scope: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    convergence_effects: tuple[str, ...] = ()
    emitted_events: tuple[str, ...] = ()
    deterministic: bool = True
    receipt_schema: str = "axm.causal-loop.module-receipt/v0.01"

    def contract(self) -> dict[str, Any]:
        return {
            "moduleId": self.module_id,
            "version": self.version,
            "reads": list(self.reads),
            "authorityScope": list(self.authority_scope),
            "dependencies": list(self.dependencies),
            "convergenceEffects": list(self.convergence_effects),
            "emittedEvents": list(self.emitted_events),
            "deterministic": self.deterministic,
            "receiptSchema": self.receipt_schema,
        }


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    predicate: Predicate = field(compare=False, repr=False)
    kind: str = "hard"

    def evaluate(self, state: Mapping[str, Any]) -> bool:
        return bool(self.predicate(state))


@dataclass(frozen=True)
class LoopSpec:
    loop_id: str
    version: str
    start_invariant: Invariant
    end_invariant: Invariant
    hard_invariants: tuple[Invariant, ...]
    soft_invariants: tuple[Invariant, ...]
    intervention_handler: InterventionHandler = field(compare=False, repr=False)
    max_waves: int = 64
    receipt_schema: str = "axm.causal-loop.run-receipt/v0.01"


class CausalLoopEngine:
    """Deterministic, headless causal-loop executor.

    Modules are evaluated against one immutable wave snapshot. Their proposed writes are
    merged atomically. Registry insertion order never decides the canonical result because
    applicable modules are sorted by module_id before merge and receipt generation.
    """

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        self.spec = spec
        self.modules = tuple(modules)
        ids = [module.module_id for module in self.modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module_id values must be unique")
        if not all(module.deterministic for module in self.modules):
            raise ValueError("v0.01 only accepts deterministic modules")

    def run(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str] = (),
        *,
        commit: bool = False,
        max_waves: int | None = None,
    ) -> dict[str, Any]:
        state: State = deepcopy(dict(initial_state))
        pristine_start = deepcopy(state)
        start_hash = deterministic_hash(pristine_start)
        limit = self.spec.max_waves if max_waves is None else max_waves
        if limit < 0:
            raise ValueError("max_waves must be >= 0")

        ordered_influences = list(influences)
        run_id = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "version": self.spec.version,
                "startStateHash": start_hash,
                "orderedExternalInfluences": ordered_influences,
            }
        )[:24]

        transitions: list[dict[str, Any]] = []
        activated: list[str] = []
        contradictions: list[dict[str, Any]] = []
        convergence_path: list[str] = [start_hash]
        max_active_workset = 0

        start_ok = self.spec.start_invariant.evaluate(state)
        if not start_ok:
            return self._receipt(
                run_id=run_id,
                pristine_start=pristine_start,
                state=state,
                influences=ordered_influences,
                transitions=transitions,
                activated=activated,
                contradictions=contradictions,
                convergence_path=convergence_path,
                status="failed",
                failure_reason="start_invariant_failed",
                commit=False,
                max_active_workset=max_active_workset,
            )

        for index, action in enumerate(ordered_influences):
            proposed = dict(self.spec.intervention_handler(action, deepcopy(state)))
            changed = {key: value for key, value in proposed.items() if state.get(key) != value}
            if changed:
                state.update(changed)
                transitions.append(
                    {
                        "kind": "external",
                        "index": index,
                        "source": action,
                        "writes": changed,
                        "stateHash": deterministic_hash(state),
                    }
                )
                convergence_path.append(deterministic_hash(state))

        seen_wave_hashes: set[str] = set()
        failure_reason: str | None = None
        status = "running"
        waves_executed = 0

        while waves_executed < limit:
            if self.spec.end_invariant.evaluate(state):
                status = "converged"
                break

            wave_hash = deterministic_hash(state)
            if wave_hash in seen_wave_hashes:
                status = "failed"
                failure_reason = "causal_cycle_detected"
                break
            seen_wave_hashes.add(wave_hash)

            snapshot = deepcopy(state)
            applicable = sorted(
                (module for module in self.modules if module.predicate(snapshot)),
                key=lambda module: module.module_id,
            )
            max_active_workset = max(max_active_workset, len(applicable))
            if not applicable:
                status = "failed"
                failure_reason = "no_relevant_module"
                break

            proposals: list[tuple[Module, dict[str, Any]]] = []
            for module in applicable:
                writes = {
                    key: value
                    for key, value in dict(module.transition(snapshot)).items()
                    if snapshot.get(key) != value
                }
                proposals.append((module, writes))

            merged: dict[str, Any] = {}
            writers: dict[str, list[str]] = {}
            for module, writes in proposals:
                for key, value in writes.items():
                    writers.setdefault(key, []).append(module.module_id)
                    if key in merged and merged[key] != value:
                        contradictions.append(
                            {
                                "wave": waves_executed,
                                "key": key,
                                "writers": writers[key],
                                "values": [merged[key], value],
                            }
                        )
                    else:
                        merged[key] = value

            if contradictions:
                status = "failed"
                failure_reason = "contradictory_writes"
                break
            if not merged:
                status = "failed"
                failure_reason = "no_state_change"
                break

            for module, writes in proposals:
                if writes:
                    activated.append(module.module_id)
                    transitions.append(
                        {
                            "kind": "module",
                            "wave": waves_executed,
                            "source": module.module_id,
                            "writes": writes,
                        }
                    )

            state.update(merged)
            waves_executed += 1
            state_hash = deterministic_hash(state)
            for item in reversed(transitions):
                if item.get("kind") != "module" or item.get("wave") != waves_executed - 1:
                    break
                item["stateHash"] = state_hash
            convergence_path.append(state_hash)

            failed_hard = [
                invariant.invariant_id
                for invariant in self.spec.hard_invariants
                if not invariant.evaluate(state)
            ]
            if failed_hard:
                status = "failed"
                failure_reason = "hard_invariant_failed:" + ",".join(sorted(failed_hard))
                break

        if status == "running":
            if self.spec.end_invariant.evaluate(state):
                status = "converged"
            else:
                status = "failed"
                failure_reason = "event_budget_exhausted"

        committed = bool(commit and status == "converged")
        return self._receipt(
            run_id=run_id,
            pristine_start=pristine_start,
            state=state,
            influences=ordered_influences,
            transitions=transitions,
            activated=activated,
            contradictions=contradictions,
            convergence_path=convergence_path,
            status=status,
            failure_reason=failure_reason,
            commit=committed,
            max_active_workset=max_active_workset,
        )

    def _receipt(
        self,
        *,
        run_id: str,
        pristine_start: State,
        state: State,
        influences: list[str],
        transitions: list[dict[str, Any]],
        activated: list[str],
        contradictions: list[dict[str, Any]],
        convergence_path: list[str],
        status: str,
        failure_reason: str | None,
        commit: bool,
        max_active_workset: int,
    ) -> dict[str, Any]:
        invariant_results = [
            {
                "id": self.spec.start_invariant.invariant_id,
                "kind": "start",
                "passed": self.spec.start_invariant.evaluate(pristine_start),
            },
            *[
                {
                    "id": invariant.invariant_id,
                    "kind": "hard",
                    "passed": invariant.evaluate(state),
                }
                for invariant in self.spec.hard_invariants
            ],
            {
                "id": self.spec.end_invariant.invariant_id,
                "kind": "hard_end",
                "passed": self.spec.end_invariant.evaluate(state),
            },
            *[
                {
                    "id": invariant.invariant_id,
                    "kind": "soft",
                    "passed": invariant.evaluate(state),
                }
                for invariant in self.spec.soft_invariants
            ],
        ]
        history_effects = (
            [
                {
                    "type": "causal_loop_committed",
                    "loopId": self.spec.loop_id,
                    "runId": run_id,
                    "endStateHash": deterministic_hash(state),
                }
            ]
            if commit
            else []
        )
        receipt = {
            "schema": self.spec.receipt_schema,
            "runId": run_id,
            "loopId": self.spec.loop_id,
            "loopVersion": self.spec.version,
            "status": status,
            "failureReason": failure_reason,
            "headless": True,
            "committed": commit,
            "startState": pristine_start,
            "startStateHash": deterministic_hash(pristine_start),
            "orderedExternalInfluences": influences,
            "modulesActivated": activated,
            "stateTransitions": transitions,
            "contradictions": contradictions,
            "convergencePath": convergence_path,
            "endState": state,
            "endStateHash": deterministic_hash(state),
            "invariantResults": invariant_results,
            "historyEffects": history_effects,
            "resourceUsage": {
                "modulesAvailable": len(self.modules),
                "moduleActivations": len(activated),
                "stateTransitions": len(transitions),
                "causalDepth": len({t.get("wave") for t in transitions if "wave" in t}),
                "externalInfluences": len(influences),
                "convergenceSteps": max(0, len(convergence_path) - 1),
                "maxActiveWorkset": max_active_workset,
                "contradictionCount": len(contradictions),
                "cpuTimeNs": None,
            },
        }
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def replay(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        replayed = self.run(
            receipt["startState"],
            receipt["orderedExternalInfluences"],
            commit=bool(receipt.get("committed", False)),
        )
        comparable_keys = (
            "runId",
            "status",
            "failureReason",
            "startStateHash",
            "orderedExternalInfluences",
            "modulesActivated",
            "stateTransitions",
            "contradictions",
            "convergencePath",
            "endStateHash",
            "invariantResults",
            "historyEffects",
        )
        replayed["replayMatches"] = all(replayed[key] == receipt[key] for key in comparable_keys)
        return replayed


def commit_receipt_to_history(receipt: Mapping[str, Any], history: list[dict[str, Any]]) -> None:
    if receipt.get("status") != "converged" or not receipt.get("committed"):
        raise ValueError("only committed, converged runs may enter persistent history")
    history.extend(deepcopy(list(receipt.get("historyEffects", []))))
