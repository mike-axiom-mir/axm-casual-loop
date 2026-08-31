from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from . import engine_legacy as _legacy

State = _legacy.State
Predicate = _legacy.Predicate
Transition = _legacy.Transition
InterventionHandler = _legacy.InterventionHandler
canonical_json = _legacy.canonical_json
deterministic_hash = _legacy.deterministic_hash
TimedInfluence = _legacy.TimedInfluence
Module = _legacy.Module
Invariant = _legacy.Invariant


@dataclass(frozen=True)
class LoopSpec(_legacy.LoopSpec):
    """Loop contract with an explicit external-direction write boundary."""

    intervention_write_scope: tuple[str, ...] = ()


class CausalLoopEngine(_legacy.CausalLoopEngine):
    """Hardened causal executor.

    v0.06 keeps the proven v0.05 module/read/checkpoint machinery while making the
    intervention boundary executable: external actors may only write declared direction
    keys. Out-of-scope handler writes fail deterministically before canonical state changes.
    """

    CHECKPOINT_SCHEMA = "axm.causal-loop.checkpoint/v0.06"

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        super().__init__(spec, modules)
        self.engine_signature = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "loopVersion": self.spec.version,
                "receiptSchema": self.spec.receipt_schema,
                "interventionWriteScope": list(self.spec.intervention_write_scope),
                "moduleContracts": [
                    module.contract()
                    for module in sorted(self.modules, key=lambda item: item.module_id)
                ],
            }
        )

    def _new_context(
        self,
        initial_state: Mapping[str, Any],
        influences: Sequence[str],
        timed_influences: Sequence[TimedInfluence | Mapping[str, Any]],
        *,
        max_waves: int | None,
    ) -> dict[str, Any]:
        context = super()._new_context(
            initial_state,
            influences,
            timed_influences,
            max_waves=max_waves,
        )
        context["intervention_authority_violations"] = []
        return context

    def _restore_checkpoint(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        context = super()._restore_checkpoint(checkpoint)
        context["intervention_authority_violations"] = []
        return context

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
                unauthorized_keys = sorted(
                    set(changed) - set(self.spec.intervention_write_scope)
                )
                if unauthorized_keys:
                    context["intervention_authority_violations"].append(
                        {
                            "wave": waves_executed,
                            "sequence": item["sequence"],
                            "action": item["action"],
                            "unauthorizedKeys": unauthorized_keys,
                            "allowedWriteKeys": list(self.spec.intervention_write_scope),
                            "proposedWrites": {
                                key: deepcopy(changed[key]) for key in unauthorized_keys
                            },
                        }
                    )
                    context["status"] = "failed"
                    context["failure_reason"] = "intervention_scope_violation"
                    return

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
                    context["failure_reason"] = "hard_invariant_failed:" + ",".join(
                        sorted(failed_hard)
                    )
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
            cycle_key = deterministic_hash(
                {"state": state, "remainingTimedInfluences": remaining}
            )
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
                    relevant = module.predicate(
                        _legacy._ModuleStateView(snapshot, module.reads)
                    )
                except _legacy._UndeclaredModuleRead as exc:
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

            context["max_active_workset"] = max(
                context["max_active_workset"], len(applicable)
            )
            if not applicable:
                context["status"] = "failed"
                context["failure_reason"] = "no_relevant_module"
                return

            proposals: list[tuple[Module, dict[str, Any]]] = []
            transition_read_violations: list[dict[str, Any]] = []
            wave_authority_violations: list[dict[str, Any]] = []
            for module in applicable:
                try:
                    raw_writes = dict(
                        module.transition(_legacy._ModuleStateView(snapshot, module.reads))
                    )
                except _legacy._UndeclaredModuleRead as exc:
                    transition_read_violations.append(
                        self._read_violation(module, waves_executed, "transition", exc.key)
                    )
                    continue
                writes = {
                    key: value
                    for key, value in raw_writes.items()
                    if snapshot.get(key) != value
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
                context["failure_reason"] = "hard_invariant_failed:" + ",".join(
                    sorted(failed_hard)
                )
                return

    def _receipt(self, context: Mapping[str, Any], *, commit: bool) -> dict[str, Any]:
        receipt = super()._receipt(context, commit=commit)
        receipt.pop("receiptHash", None)
        receipt["interventionWriteScope"] = list(self.spec.intervention_write_scope)
        receipt["interventionAuthorityViolations"] = deepcopy(
            context.get("intervention_authority_violations", [])
        )
        receipt["resourceUsage"]["interventionAuthorityViolationCount"] = len(
            context.get("intervention_authority_violations", [])
        )
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def replay(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        replayed = super().replay(receipt)
        replayed["replayMatches"] = bool(
            replayed["replayMatches"]
            and replayed.get("interventionWriteScope")
            == receipt.get("interventionWriteScope")
            and replayed.get("interventionAuthorityViolations")
            == receipt.get("interventionAuthorityViolations")
        )
        return replayed


commit_receipt_to_history = _legacy.commit_receipt_to_history
