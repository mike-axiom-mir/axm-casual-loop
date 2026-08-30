from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

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
    """External direction scheduled immediately before a deterministic causal wave."""

    at_wave: int
    action: str

    def __post_init__(self) -> None:
        if not isinstance(self.at_wave, int) or isinstance(self.at_wave, bool) or self.at_wave < 0:
            raise ValueError("at_wave must be a non-negative integer")
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("action must be a non-empty string")

    def contract(self, sequence: int) -> dict[str, Any]:
        return {"atWave": self.at_wave, "sequence": sequence, "action": self.action}


class _UndeclaredModuleRead(RuntimeError):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class _ModuleStateView(Mapping[str, Any]):
    """Read-only state view limited to one module's declared read contract."""

    def __init__(self, state: Mapping[str, Any], allowed_keys: Sequence[str]):
        self._state = state
        self._allowed = frozenset(allowed_keys)

    def __getitem__(self, key: str) -> Any:
        if key not in self._allowed:
            raise _UndeclaredModuleRead(key)
        return self._state[key]

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(key for key in self._allowed if key in self._state))

    def __len__(self) -> int:
        return sum(key in self._state for key in self._allowed)


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
    receipt_schema: str = "axm.causal-loop.run-receipt/v0.05"


class CausalLoopEngine:
    """Deterministic, headless causal-loop executor.

    Modules in one wave read a frozen state snapshot and propose writes. Applicable modules
    are sorted by module_id and writes are merged atomically, so registry/completion order
    cannot silently decide canonical truth.

    v0.02: timed external direction enters before an explicit causal wave.
    v0.03: a running deterministic context can be checkpointed between waves and resumed
    without re-executing the already committed prefix of that run.
    v0.04: declared module authority scopes are enforced before any proposed write can
    enter the deterministic merge.
    v0.05: predicates and transitions receive only their declared read keys; undeclared
    reads fail explicitly before a wave can commit.
    """

    CHECKPOINT_SCHEMA = "axm.causal-loop.checkpoint/v0.05"

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        self.spec = spec
        self.modules = tuple(modules)
        ids = [module.module_id for module in self.modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module_id values must be unique")
        if not all(module.deterministic for module in self.modules):
            raise ValueError("causal loop only accepts deterministic modules")
        self.engine_signature = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "loopVersion": self.spec.version,
                "receiptSchema": self.spec.receipt_schema,
                "moduleContracts": [
                    module.contract() for module in sorted(self.modules, key=lambda item: item.module_id)
                ],
            }
        )

    def run(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str] = (),
        *,
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]] = (),
        commit: bool = False,
        max_waves: int | None = None,
    ) -> dict[str, Any]:
        context = self._new_context(initial_state, influences, timed_influences, max_waves=max_waves)
        self._execute(context)
        return self._receipt(context, commit=bool(commit and context["status"] == "converged"))

    def pause(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str] = (),
        *,
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]] = (),
        after_waves: int,
        max_waves: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(after_waves, int) or isinstance(after_waves, bool) or after_waves < 0:
            raise ValueError("after_waves must be a non-negative integer")
        context = self._new_context(initial_state, influences, timed_influences, max_waves=max_waves)
        self._execute(context, pause_after_waves=after_waves)
        if context["status"] != "paused":
            raise ValueError(f"run became {context['status']} before checkpoint wave {after_waves}")
        return self._checkpoint(context)

    def resume(
        self,
        checkpoint: Mapping[str, Any],
        *,
        commit: bool = False,
        max_waves: int | None = None,
    ) -> dict[str, Any]:
        context = self._restore_checkpoint(checkpoint)
        if max_waves is not None:
            if max_waves < context["waves_executed"]:
                raise ValueError("max_waves cannot be below checkpoint causal depth")
            context["max_waves"] = max_waves
        context["status"] = "running"
        context["failure_reason"] = None
        self._execute(context)
        return self._receipt(context, commit=bool(commit and context["status"] == "converged"))

    def _new_context(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str],
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]],
        *,
        max_waves: int | None,
    ) -> dict[str, Any]:
        if influences and timed_influences:
            raise ValueError("use legacy influences or timed_influences, not both")
        state: State = deepcopy(dict(initial_state))
        pristine_start = deepcopy(state)
        limit = self.spec.max_waves if max_waves is None else max_waves
        if limit < 0:
            raise ValueError("max_waves must be >= 0")
        schedule = self._normalize_schedule(influences, timed_influences)
        start_hash = deterministic_hash(pristine_start)
        run_id = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "version": self.spec.version,
                "startStateHash": start_hash,
                "timedExternalInfluences": schedule,
            }
        )[:24]
        context = {
            "run_id": run_id,
            "pristine_start": pristine_start,
            "state": state,
            "ordered_influences": [item["action"] for item in schedule],
            "schedule": schedule,
            "applied_schedule": [],
            "transitions": [],
            "activated": [],
            "contradictions": [],
            "authority_violations": [],
            "read_violations": [],
            "convergence_path": [start_hash],
            "seen_cycle_keys": [],
            "max_active_workset": 0,
            "waves_executed": 0,
            "max_waves": limit,
            "status": "running",
            "failure_reason": None,
        }
        if not self.spec.start_invariant.evaluate(state):
            context["status"] = "failed"
            context["failure_reason"] = "start_invariant_failed"
        return context

    @staticmethod
    def _read_violation(module: Module, wave: int, phase: str, key: str) -> dict[str, Any]:
        return {
            "wave": wave,
            "moduleId": module.module_id,
            "phase": phase,
            "undeclaredKey": key,
            "declaredReads": list(module.reads),
        }

    def _execute(self, context: dict[str, Any], *, pause_after_waves: int | None = None) -> None:
        if context["status"] != "running":
            return

        while True:
            state: State = context["state"]
            waves_executed: int = context["waves_executed"]

            if self.spec.end_invariant.evaluate(state):
                context["status"] = "converged"
                return

            if pause_after_waves is not None and waves_executed >= pause_after_waves:
                context["status"] = "paused"
                return

            applied_sequences = {item["sequence"] for item in context["applied_schedule"]}
            due = [
                item
                for item in context["schedule"]
                if item["atWave"] == waves_executed and item["sequence"] not in applied_sequences
            ]
            for item in due:
                proposed = dict(self.spec.intervention_handler(item["action"], deepcopy(state)))
                changed = {key: value for key, value in proposed.items() if state.get(key) != value}
                context["applied_schedule"].append({**item, "writes": changed})
                if changed:
                    state.update(changed)
                    state_hash = deterministic_hash(state)
                    context["transitions"].append(
                        {
                            "kind": "external",
                            "wave": waves_executed,
                            "sequence": item["sequence"],
                            "source": item["action"],
                            "writes": changed,
                            "stateHash": state_hash,
                        }
                    )
                    context["convergence_path"].append(state_hash)
                failed_hard = self._failed_hard_invariants(state)
                if failed_hard:
                    context["status"] = "failed"
                    context["failure_reason"] = "hard_invariant_failed:" + ",".join(sorted(failed_hard))
                    return

            if self.spec.end_invariant.evaluate(state):
                context["status"] = "converged"
                return

            if waves_executed >= context["max_waves"]:
                context["status"] = "failed"
                context["failure_reason"] = "event_budget_exhausted"
                return

            remaining = [
                {
                    "afterWaves": item["atWave"] - waves_executed,
                    "sequence": item["sequence"],
                    "action": item["action"],
                }
                for item in context["schedule"]
                if item["atWave"] > waves_executed
            ]
            cycle_key = deterministic_hash({"state": state, "remainingTimedInfluences": remaining})
            if cycle_key in context["seen_cycle_keys"]:
                context["status"] = "failed"
                context["failure_reason"] = "causal_cycle_detected"
                return
            context["seen_cycle_keys"].append(cycle_key)

            snapshot = deepcopy(state)
            applicable: list[Module] = []
            predicate_read_violations: list[dict[str, Any]] = []
            for module in sorted(self.modules, key=lambda item: item.module_id):
                try:
                    relevant = module.predicate(_ModuleStateView(snapshot, module.reads))
                except _UndeclaredModuleRead as exc:
                    predicate_read_violations.append(
                        self._read_violation(module, waves_executed, "predicate", exc.key)
                    )
                    continue
                if relevant:
                    applicable.append(module)

            if predicate_read_violations:
                context["read_violations"].extend(predicate_read_violations)
                context["status"] = "failed"
                context["failure_reason"] = "read_scope_violation"
                return

            context["max_active_workset"] = max(context["max_active_workset"], len(applicable))
            if not applicable:
                context["status"] = "failed"
                context["failure_reason"] = "no_relevant_module"
                return

            proposals: list[tuple[Module, dict[str, Any]]] = []
            transition_read_violations: list[dict[str, Any]] = []
            wave_authority_violations: list[dict[str, Any]] = []
            for module in applicable:
                try:
                    raw_writes = dict(module.transition(_ModuleStateView(snapshot, module.reads)))
                except _UndeclaredModuleRead as exc:
                    transition_read_violations.append(
                        self._read_violation(module, waves_executed, "transition", exc.key)
                    )
                    continue
                writes = {
                    key: value for key, value in raw_writes.items() if snapshot.get(key) != value
                }
                unauthorized_keys = sorted(set(writes) - set(module.authority_scope))
                if unauthorized_keys:
                    wave_authority_violations.append(
                        {
                            "wave": waves_executed,
                            "moduleId": module.module_id,
                            "unauthorizedKeys": unauthorized_keys,
                            "proposedWrites": {
                                key: deepcopy(writes[key]) for key in unauthorized_keys
                            },
                        }
                    )
                proposals.append((module, writes))

            if transition_read_violations:
                context["read_violations"].extend(transition_read_violations)
                context["status"] = "failed"
                context["failure_reason"] = "read_scope_violation"
                return

            if wave_authority_violations:
                context["authority_violations"].extend(wave_authority_violations)
                context["status"] = "failed"
                context["failure_reason"] = "authority_scope_violation"
                return

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

            context["contradictions"].extend(wave_contradictions)
            if wave_contradictions:
                context["status"] = "failed"
                context["failure_reason"] = "contradictory_writes"
                return
            if not merged:
                context["status"] = "failed"
                context["failure_reason"] = "no_state_change"
                return

            for module, writes in proposals:
                if writes:
                    context["activated"].append(module.module_id)
                    context["transitions"].append(
                        {
                            "kind": "module",
                            "wave": waves_executed,
                            "source": module.module_id,
                            "writes": writes,
                        }
                    )

            state.update(merged)
            state_hash = deterministic_hash(state)
            for item in reversed(context["transitions"]):
                if item.get("kind") != "module" or item.get("wave") != waves_executed:
                    break
                item["stateHash"] = state_hash
            context["convergence_path"].append(state_hash)
            context["waves_executed"] += 1

            failed_hard = self._failed_hard_invariants(state)
            if failed_hard:
                context["status"] = "failed"
                context["failure_reason"] = "hard_invariant_failed:" + ",".join(sorted(failed_hard))
                return

    def _checkpoint(self, context: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "schema": self.CHECKPOINT_SCHEMA,
            "engineSignature": self.engine_signature,
            "loopId": self.spec.loop_id,
            "loopVersion": self.spec.version,
            "runId": context["run_id"],
            "startState": deepcopy(context["pristine_start"]),
            "state": deepcopy(context["state"]),
            "stateHash": deterministic_hash(context["state"]),
            "orderedExternalInfluences": deepcopy(context["ordered_influences"]),
            "timedExternalInfluences": deepcopy(context["schedule"]),
            "appliedTimedInfluences": deepcopy(context["applied_schedule"]),
            "modulesActivated": deepcopy(context["activated"]),
            "stateTransitions": deepcopy(context["transitions"]),
            "contradictions": deepcopy(context["contradictions"]),
            "authorityViolations": deepcopy(context["authority_violations"]),
            "readViolations": deepcopy(context["read_violations"]),
            "convergencePath": deepcopy(context["convergence_path"]),
            "seenCycleKeys": deepcopy(context["seen_cycle_keys"]),
            "maxActiveWorkset": context["max_active_workset"],
            "wavesExecuted": context["waves_executed"],
            "maxWaves": context["max_waves"],
        }
        payload["checkpointHash"] = deterministic_hash(payload)
        return payload

    def _restore_checkpoint(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        data = deepcopy(dict(checkpoint))
        checkpoint_hash = data.pop("checkpointHash", None)
        if checkpoint_hash is None or deterministic_hash(data) != checkpoint_hash:
            raise ValueError("checkpoint hash mismatch")
        data["checkpointHash"] = checkpoint_hash
        if data.get("schema") != self.CHECKPOINT_SCHEMA:
            raise ValueError("unsupported checkpoint schema")
        if data.get("engineSignature") != self.engine_signature:
            raise ValueError("checkpoint engine signature mismatch")
        if data.get("loopId") != self.spec.loop_id or data.get("loopVersion") != self.spec.version:
            raise ValueError("checkpoint loop identity mismatch")
        if deterministic_hash(data["state"]) != data.get("stateHash"):
            raise ValueError("checkpoint state hash mismatch")

        expected_run_id = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "version": self.spec.version,
                "startStateHash": deterministic_hash(data["startState"]),
                "timedExternalInfluences": data["timedExternalInfluences"],
            }
        )[:24]
        if expected_run_id != data.get("runId"):
            raise ValueError("checkpoint run identity mismatch")

        return {
            "run_id": data["runId"],
            "pristine_start": data["startState"],
            "state": data["state"],
            "ordered_influences": data["orderedExternalInfluences"],
            "schedule": data["timedExternalInfluences"],
            "applied_schedule": data["appliedTimedInfluences"],
            "transitions": data["stateTransitions"],
            "activated": data["modulesActivated"],
            "contradictions": data["contradictions"],
            "authority_violations": data["authorityViolations"],
            "read_violations": data["readViolations"],
            "convergence_path": data["convergencePath"],
            "seen_cycle_keys": data["seenCycleKeys"],
            "max_active_workset": data["maxActiveWorkset"],
            "waves_executed": data["wavesExecuted"],
            "max_waves": data["maxWaves"],
            "status": "running",
            "failure_reason": None,
        }

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

    def _receipt(self, context: Mapping[str, Any], *, commit: bool) -> dict[str, Any]:
        state = context["state"]
        pristine_start = context["pristine_start"]
        invariant_results = [
            {
                "id": self.spec.start_invariant.invariant_id,
                "kind": "start",
                "passed": self.spec.start_invariant.evaluate(pristine_start),
            },
            *[
                {"id": inv.invariant_id, "kind": "hard", "passed": inv.evaluate(state)}
                for inv in self.spec.hard_invariants
            ],
            {
                "id": self.spec.end_invariant.invariant_id,
                "kind": "hard_end",
                "passed": self.spec.end_invariant.evaluate(state),
            },
            *[
                {"id": inv.invariant_id, "kind": "soft", "passed": inv.evaluate(state)}
                for inv in self.spec.soft_invariants
            ],
        ]
        history_effects = (
            [
                {
                    "type": "causal_loop_committed",
                    "loopId": self.spec.loop_id,
                    "runId": context["run_id"],
                    "endStateHash": deterministic_hash(state),
                }
            ]
            if commit
            else []
        )
        applied_sequences = {item["sequence"] for item in context["applied_schedule"]}
        unapplied = [
            item for item in context["schedule"] if item["sequence"] not in applied_sequences
        ]
        receipt = {
            "schema": self.spec.receipt_schema,
            "runId": context["run_id"],
            "loopId": self.spec.loop_id,
            "loopVersion": self.spec.version,
            "status": context["status"],
            "failureReason": context["failure_reason"],
            "headless": True,
            "committed": commit,
            "startState": deepcopy(pristine_start),
            "startStateHash": deterministic_hash(pristine_start),
            "orderedExternalInfluences": deepcopy(context["ordered_influences"]),
            "timedExternalInfluences": deepcopy(context["schedule"]),
            "appliedTimedInfluences": deepcopy(context["applied_schedule"]),
            "unappliedTimedInfluences": deepcopy(unapplied),
            "modulesActivated": deepcopy(context["activated"]),
            "stateTransitions": deepcopy(context["transitions"]),
            "contradictions": deepcopy(context["contradictions"]),
            "authorityViolations": deepcopy(context["authority_violations"]),
            "readViolations": deepcopy(context["read_violations"]),
            "convergencePath": deepcopy(context["convergence_path"]),
            "endState": deepcopy(state),
            "endStateHash": deterministic_hash(state),
            "invariantResults": invariant_results,
            "historyEffects": history_effects,
            "resourceUsage": {
                "modulesAvailable": len(self.modules),
                "moduleActivations": len(context["activated"]),
                "stateTransitions": len(context["transitions"]),
                "causalDepth": context["waves_executed"],
                "externalInfluences": len(context["applied_schedule"]),
                "scheduledExternalInfluences": len(context["schedule"]),
                "convergenceSteps": max(0, len(context["convergence_path"]) - 1),
                "maxActiveWorkset": context["max_active_workset"],
                "contradictionCount": len(context["contradictions"]),
                "authorityViolationCount": len(context["authority_violations"]),
                "readViolationCount": len(context["read_violations"]),
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
            "runId", "status", "failureReason", "startStateHash",
            "orderedExternalInfluences", "timedExternalInfluences",
            "appliedTimedInfluences", "unappliedTimedInfluences",
            "modulesActivated", "stateTransitions", "contradictions", "authorityViolations",
            "readViolations", "convergencePath", "endStateHash", "invariantResults",
            "historyEffects",
        )
        replayed["replayMatches"] = all(replayed[key] == receipt[key] for key in comparable_keys)
        return replayed


def commit_receipt_to_history(receipt: Mapping[str, Any], history: list[dict[str, Any]]) -> None:
    if receipt.get("status") != "converged" or not receipt.get("committed"):
        raise ValueError("only committed, converged runs may enter persistent history")
    history.extend(deepcopy(list(receipt.get("historyEffects", []))))
