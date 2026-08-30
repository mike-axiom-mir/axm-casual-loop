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
class TimedInfluence:
    """One external direction scheduled before a deterministic causal wave."""

    at_wave: int
    action: str

    def __post_init__(self) -> None:
        if not isinstance(self.at_wave, int) or isinstance(self.at_wave, bool) or self.at_wave < 0:
            raise ValueError("at_wave must be a non-negative integer")
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("action must be a non-empty string")

    def contract(self, sequence: int) -> dict[str, Any]:
        return {"atWave": self.at_wave, "sequence": sequence, "action": self.action}


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
    receipt_schema: str = "axm.causal-loop.run-receipt/v0.02"


class CausalLoopEngine:
    """Deterministic, headless causal-loop executor.

    Modules in a wave read one immutable state snapshot and propose writes. Applicable
    modules are sorted by module_id and their writes are merged atomically, so registry or
    completion order cannot silently decide canonical truth.

    v0.02 adds timed external direction. A TimedInfluence enters immediately before its
    declared causal wave. Timing is therefore part of the deterministic input contract and
    of the run identity/replay evidence.
    """

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        self.spec = spec
        self.modules = tuple(modules)
        ids = [module.module_id for module in self.modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module_id values must be unique")
        if not all(module.deterministic for module in self.modules):
            raise ValueError("causal loop only accepts deterministic modules")

    def run(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str] = (),
        *,
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]] = (),
        commit: bool = False,
        max_waves: int | None = None,
    ) -> dict[str, Any]:
        if influences and timed_influences:
            raise ValueError("use legacy influences or timed_influences, not both")

        state: State = deepcopy(dict(initial_state))
        pristine_start = deepcopy(state)
        start_hash = deterministic_hash(pristine_start)
        limit = self.spec.max_waves if max_waves is None else max_waves
        if limit < 0:
            raise ValueError("max_waves must be >= 0")

        schedule = self._normalize_schedule(influences, timed_influences)
        ordered_influences = [item["action"] for item in schedule]
        run_id = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "version": self.spec.version,
                "startStateHash": start_hash,
                "timedExternalInfluences": schedule,
            }
        )[:24]

        transitions: list[dict[str, Any]] = []
        activated: list[str] = []
        contradictions: list[dict[str, Any]] = []
        convergence_path: list[str] = [start_hash]
        applied_schedule: list[dict[str, Any]] = []
        max_active_workset = 0

        start_ok = self.spec.start_invariant.evaluate(state)
        if not start_ok:
            return self._receipt(
                run_id=run_id,
                pristine_start=pristine_start,
                state=state,
                influences=ordered_influences,
                schedule=schedule,
                applied_schedule=applied_schedule,
                transitions=transitions,
                activated=activated,
                contradictions=contradictions,
                convergence_path=convergence_path,
                status="failed",
                failure_reason="start_invariant_failed",
                commit=False,
                max_active_workset=max_active_workset,
                waves_executed=0,
            )

        seen_cycle_keys: set[str] = set()
        failure_reason: str | None = None
        status = "running"
        waves_executed = 0

        while True:
            if self.spec.end_invariant.evaluate(state):
                status = "converged"
                break

            due = [item for item in schedule if item["atWave"] == waves_executed]
            for item in due:
                proposed = dict(self.spec.intervention_handler(item["action"], deepcopy(state)))
                changed = {key: value for key, value in proposed.items() if state.get(key) != value}
                applied = {**item, "writes": changed}
                applied_schedule.append(applied)
                if changed:
                    state.update(changed)
                    state_hash = deterministic_hash(state)
                    transitions.append(
                        {
                            "kind": "external",
                            "wave": waves_executed,
                            "sequence": item["sequence"],
                            "source": item["action"],
                            "writes": changed,
                            "stateHash": state_hash,
                        }
                    )
                    convergence_path.append(state_hash)

                failed_hard = self._failed_hard_invariants(state)
                if failed_hard:
                    status = "failed"
                    failure_reason = "hard_invariant_failed:" + ",".join(sorted(failed_hard))
                    break
            if status == "failed":
                break

            if self.spec.end_invariant.evaluate(state):
                status = "converged"
                break

            if waves_executed >= limit:
                status = "failed"
                failure_reason = "event_budget_exhausted"
                break

            remaining = [
                {
                    "afterWaves": item["atWave"] - waves_executed,
                    "sequence": item["sequence"],
                    "action": item["action"],
                }
                for item in schedule
                if item["atWave"] > waves_executed
            ]
            cycle_key = deterministic_hash({"state": state, "remainingTimedInfluences": remaining})
            if cycle_key in seen_cycle_keys:
                status = "failed"
                failure_reason = "causal_cycle_detected"
                break
            seen_cycle_keys.add(cycle_key)

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
            wave_contradictions: list[dict[str, Any]] = []
            for module, writes in proposals:
                for key, value in writes.items():
                    writers.setdefault(key, []).append(module.module_id)
                    if key in merged and merged[key] != value:
                        wave_contradictions.append(
                            {
                                "wave": waves_executed,
                                "key": key,
                                "writers": list(writers[key]),
                                "values": [merged[key], value],
                            }
                        )
                    else:
                        merged[key] = value

            contradictions.extend(wave_contradictions)
            if wave_contradictions:
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
            state_hash = deterministic_hash(state)
            for item in reversed(transitions):
                if item.get("kind") != "module" or item.get("wave") != waves_executed:
                    break
                item["stateHash"] = state_hash
            convergence_path.append(state_hash)
            waves_executed += 1

            failed_hard = self._failed_hard_invariants(state)
            if failed_hard:
                status = "failed"
                failure_reason = "hard_invariant_failed:" + ",".join(sorted(failed_hard))
                break

        committed = bool(commit and status == "converged")
        return self._receipt(
            run_id=run_id,
            pristine_start=pristine_start,
            state=state,
            influences=ordered_influences,
            schedule=schedule,
            applied_schedule=applied_schedule,
            transitions=transitions,
            activated=activated,
            contradictions=contradictions,
            convergence_path=convergence_path,
            status=status,
            failure_reason=failure_reason,
            commit=committed,
            max_active_workset=max_active_workset,
            waves_executed=waves_executed,
        )

    @staticmethod
    def _normalize_schedule(
        influences: Sequence[str],
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        raw: list[TimedInfluence] = []
        if timed_influences:
            for item in timed_influences:
                if isinstance(item, TimedInfluence):
                    raw.append(item)
                    continue
                try:
                    raw.append(TimedInfluence(at_wave=item["atWave"], action=item["action"]))
                except (KeyError, TypeError) as exc:
                    raise ValueError("timed influence requires atWave and action") from exc
        else:
            raw = [TimedInfluence(at_wave=0, action=action) for action in influences]

        schedule = [item.contract(sequence=index) for index, item in enumerate(raw)]
        return sorted(schedule, key=lambda item: (item["atWave"], item["sequence"]))

    def _failed_hard_invariants(self, state: Mapping[str, Any]) -> list[str]:
        return [
            invariant.invariant_id
            for invariant in self.spec.hard_invariants
            if not invariant.evaluate(state)
        ]

    def _receipt(
        self,
        *,
        run_id: str,
        pristine_start: State,
        state: State,
        influences: list[str],
        schedule: list[dict[str, Any]],
        applied_schedule: list[dict[str, Any]],
        transitions: list[dict[str, Any]],
        activated: list[str],
        contradictions: list[dict[str, Any]],
        convergence_path: list[str],
        status: str,
        failure_reason: str | None,
        commit: bool,
        max_active_workset: int,
        waves_executed: int,
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
        applied_sequences = {item["sequence"] for item in applied_schedule}
        unapplied = [item for item in schedule if item["sequence"] not in applied_sequences]
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
            "timedExternalInfluences": schedule,
            "appliedTimedInfluences": applied_schedule,
            "unappliedTimedInfluences": unapplied,
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
                "causalDepth": waves_executed,
                "externalInfluences": len(applied_schedule),
                "scheduledExternalInfluences": len(schedule),
                "convergenceSteps": max(0, len(convergence_path) - 1),
                "maxActiveWorkset": max_active_workset,
                "contradictionCount": len(contradictions),
                "cpuTimeNs": None,
            },
        }
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def replay(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        if "timedExternalInfluences" in receipt:
            replayed = self.run(
                receipt["startState"],
                timed_influences=receipt["timedExternalInfluences"],
                commit=bool(receipt.get("committed", False)),
            )
        else:
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
            "timedExternalInfluences",
            "appliedTimedInfluences",
            "unappliedTimedInfluences",
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
