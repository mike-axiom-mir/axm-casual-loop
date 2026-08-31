from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

from . import engine_v06 as _v06

State = _v06.State
Predicate = _v06.Predicate
Transition = _v06.Transition
InterventionHandler = _v06.InterventionHandler
canonical_json = _v06.canonical_json
deterministic_hash = _v06.deterministic_hash
TimedInfluence = _v06.TimedInfluence
Module = _v06.Module
Invariant = _v06.Invariant
LoopSpec = _v06.LoopSpec

DEPENDENCY_POLICY = "all-prior-activation/v0.01"


class CausalLoopEngine(_v06.CausalLoopEngine):
    """Hardened causal executor with executable module dependencies.

    v0.07 keeps the proven v0.06 intervention/read/write/checkpoint machinery and makes
    ``Module.dependencies`` causal instead of descriptive. Every declared dependency must
    name a registered module, dependency graphs must be acyclic, and a dependent module may
    execute only after all dependencies activated in an earlier committed causal wave.
    Same-wave module order can never satisfy a dependency.
    """

    CHECKPOINT_SCHEMA = "axm.causal-loop.checkpoint/v0.07"

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        original_modules = tuple(modules)
        self._validate_dependencies(original_modules)
        self._dependency_context: ContextVar[dict[str, Any] | None] = ContextVar(
            f"axm_causal_dependency_context_{id(self)}",
            default=None,
        )
        wrapped_modules = tuple(self._with_dependency_gate(module) for module in original_modules)
        super().__init__(spec, wrapped_modules)
        self.engine_signature = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "loopVersion": self.spec.version,
                "receiptSchema": self.spec.receipt_schema,
                "interventionWriteScope": list(self.spec.intervention_write_scope),
                "dependencyPolicy": DEPENDENCY_POLICY,
                "moduleContracts": [
                    module.contract()
                    for module in sorted(self.modules, key=lambda item: item.module_id)
                ],
            }
        )

    @staticmethod
    def _validate_dependencies(modules: Sequence[Module]) -> None:
        ids = [module.module_id for module in modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module_id values must be unique")
        id_set = set(ids)
        graph: dict[str, tuple[str, ...]] = {}

        for module in modules:
            dependencies = tuple(module.dependencies)
            if len(dependencies) != len(set(dependencies)):
                raise ValueError(f"module {module.module_id} has duplicate dependencies")
            if module.module_id in dependencies:
                raise ValueError(f"module {module.module_id} cannot depend on itself")
            missing = sorted(set(dependencies) - id_set)
            if missing:
                raise ValueError(
                    f"module {module.module_id} depends on unknown module(s): {', '.join(missing)}"
                )
            graph[module.module_id] = dependencies

        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []

        def visit(module_id: str) -> None:
            if module_id in visited:
                return
            if module_id in visiting:
                start = stack.index(module_id)
                cycle = stack[start:] + [module_id]
                raise ValueError("dependency cycle detected: " + " -> ".join(cycle))
            visiting.add(module_id)
            stack.append(module_id)
            for dependency in sorted(graph[module_id]):
                visit(dependency)
            stack.pop()
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in sorted(graph):
            visit(module_id)

    def _with_dependency_gate(self, module: Module) -> Module:
        if not module.dependencies:
            return module
        original_predicate = module.predicate

        def gated_predicate(state: Mapping[str, Any]) -> bool:
            relevant = bool(original_predicate(state))
            if not relevant:
                return False
            context = self._dependency_context.get()
            if context is None:
                return True

            activated = set(context["activated"])
            missing = [dependency for dependency in module.dependencies if dependency not in activated]
            if not missing:
                return True

            block = {
                "wave": context["waves_executed"],
                "moduleId": module.module_id,
                "requiredDependencies": list(module.dependencies),
                "missingDependencies": missing,
            }
            blocks = context.setdefault("dependency_blocks", [])
            if block not in blocks:
                blocks.append(block)
            return False

        return replace(module, predicate=gated_predicate)

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
        context["dependency_blocks"] = []
        return context

    def _execute(self, context: dict[str, Any], *, pause_after_waves: int | None = None) -> None:
        token = self._dependency_context.set(context)
        try:
            super()._execute(context, pause_after_waves=pause_after_waves)
        finally:
            self._dependency_context.reset(token)

        if context["status"] == "failed" and context["failure_reason"] == "no_relevant_module":
            current_wave_blocks = [
                block
                for block in context.get("dependency_blocks", [])
                if block["wave"] == context["waves_executed"]
            ]
            if current_wave_blocks:
                context["failure_reason"] = "unsatisfied_dependencies"

    def _checkpoint(self, context: Mapping[str, Any]) -> dict[str, Any]:
        checkpoint = super()._checkpoint(context)
        checkpoint.pop("checkpointHash", None)
        checkpoint["dependencyPolicy"] = DEPENDENCY_POLICY
        checkpoint["dependencyBlocks"] = deepcopy(context.get("dependency_blocks", []))
        checkpoint["checkpointHash"] = deterministic_hash(checkpoint)
        return checkpoint

    def _restore_checkpoint(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        if checkpoint.get("dependencyPolicy") != DEPENDENCY_POLICY:
            raise ValueError("checkpoint dependency policy mismatch")
        context = super()._restore_checkpoint(checkpoint)
        context["dependency_blocks"] = deepcopy(list(checkpoint.get("dependencyBlocks", [])))
        return context

    def _receipt(self, context: Mapping[str, Any], *, commit: bool) -> dict[str, Any]:
        receipt = super()._receipt(context, commit=commit)
        receipt.pop("receiptHash", None)
        blocks = deepcopy(list(context.get("dependency_blocks", [])))
        receipt["dependencyPolicy"] = DEPENDENCY_POLICY
        receipt["dependencyBlocks"] = blocks
        receipt["resourceUsage"]["dependencyBlockCount"] = len(blocks)
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def replay(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        replayed = super().replay(receipt)
        replayed["replayMatches"] = bool(
            replayed["replayMatches"]
            and replayed.get("dependencyPolicy") == receipt.get("dependencyPolicy")
            and replayed.get("dependencyBlocks") == receipt.get("dependencyBlocks")
        )
        return replayed


commit_receipt_to_history = _v06.commit_receipt_to_history
