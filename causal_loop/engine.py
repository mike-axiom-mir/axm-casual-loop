from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from . import engine_v07 as _v07

State = _v07.State
Predicate = _v07.Predicate
Transition = _v07.Transition
InterventionHandler = _v07.InterventionHandler
canonical_json = _v07.canonical_json
deterministic_hash = _v07.deterministic_hash
TimedInfluence = _v07.TimedInfluence
Module = _v07.Module
Invariant = _v07.Invariant
DEPENDENCY_POLICY = _v07.DEPENDENCY_POLICY

CONVERGENCE_EFFECT_POLICY = "required-committed-effects/v0.01"


@dataclass(frozen=True)
class LoopSpec(_v07.LoopSpec):
    """Loop contract with optional named convergence evidence requirements."""

    required_convergence_effects: tuple[str, ...] = ()


class CausalLoopEngine(_v07.CausalLoopEngine):
    """Hardened causal executor with executable convergence-effect evidence.

    v0.08 keeps the v0.07 dependency/read/write/intervention/checkpoint machinery and
    makes ``Module.convergence_effects`` observable and enforceable. The raw end invariant
    remains mandatory. A required convergence effect is additional proof and counts only
    after a module declaring that effect has actually committed a state-changing activation.
    """

    CHECKPOINT_SCHEMA = "axm.causal-loop.checkpoint/v0.08"

    def __init__(self, spec: LoopSpec, modules: Iterable[Module]):
        original_modules = tuple(modules)
        self._validate_convergence_contract(spec, original_modules)
        self._raw_end_invariant = spec.end_invariant
        self._module_effects = {
            module.module_id: tuple(module.convergence_effects)
            for module in original_modules
        }
        self._convergence_context: ContextVar[dict[str, Any] | None] = ContextVar(
            f"axm_causal_convergence_context_{id(self)}",
            default=None,
        )

        raw_end = self._raw_end_invariant

        def gated_end(state: Mapping[str, Any]) -> bool:
            raw_passed = raw_end.evaluate(state)
            if not raw_passed:
                return False
            context = self._convergence_context.get()
            if context is None:
                # Receipt construction happens outside the executor context. The receipt
                # override below writes the effective hard-end result explicitly.
                return True
            missing = self._missing_required_effects(context)
            if not missing:
                return True
            block = {
                "wave": context["waves_executed"],
                "requiredEffects": list(self.spec.required_convergence_effects),
                "realizedEffects": self._realized_effects(context),
                "missingEffects": missing,
            }
            blocks = context.setdefault("convergence_effect_blocks", [])
            if block not in blocks:
                blocks.append(block)
            return False

        guarded_spec = replace(
            spec,
            end_invariant=Invariant(raw_end.invariant_id, gated_end, raw_end.kind),
        )
        super().__init__(guarded_spec, original_modules)
        self.engine_signature = deterministic_hash(
            {
                "loopId": self.spec.loop_id,
                "loopVersion": self.spec.version,
                "receiptSchema": self.spec.receipt_schema,
                "interventionWriteScope": list(self.spec.intervention_write_scope),
                "dependencyPolicy": DEPENDENCY_POLICY,
                "convergenceEffectPolicy": CONVERGENCE_EFFECT_POLICY,
                "requiredConvergenceEffects": list(self.spec.required_convergence_effects),
                "moduleContracts": [
                    module.contract()
                    for module in sorted(self.modules, key=lambda item: item.module_id)
                ],
            }
        )

    @staticmethod
    def _validate_convergence_contract(spec: LoopSpec, modules: Sequence[Module]) -> None:
        required = tuple(spec.required_convergence_effects)
        if len(required) != len(set(required)):
            raise ValueError("required convergence effects must be unique")
        if any(not isinstance(effect, str) or not effect for effect in required):
            raise ValueError("required convergence effects must be non-empty strings")

        declared: set[str] = set()
        for module in modules:
            effects = tuple(module.convergence_effects)
            if len(effects) != len(set(effects)):
                raise ValueError(
                    f"module {module.module_id} has duplicate convergence effects"
                )
            if any(not isinstance(effect, str) or not effect for effect in effects):
                raise ValueError(
                    f"module {module.module_id} has invalid convergence effect"
                )
            declared.update(effects)

        missing = sorted(set(required) - declared)
        if missing:
            raise ValueError(
                "required convergence effect(s) are not declared by any module: "
                + ", ".join(missing)
            )

    def _realized_effects(self, context: Mapping[str, Any]) -> list[str]:
        effects: set[str] = set()
        for module_id in context.get("activated", []):
            effects.update(self._module_effects.get(module_id, ()))
        return sorted(effects)

    def _missing_required_effects(self, context: Mapping[str, Any]) -> list[str]:
        realized = set(self._realized_effects(context))
        return [
            effect
            for effect in self.spec.required_convergence_effects
            if effect not in realized
        ]

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
        context["convergence_effect_blocks"] = []
        return context

    def _execute(self, context: dict[str, Any], *, pause_after_waves: int | None = None) -> None:
        token = self._convergence_context.set(context)
        try:
            super()._execute(context, pause_after_waves=pause_after_waves)
        finally:
            self._convergence_context.reset(token)

        if context["status"] == "failed" and context["failure_reason"] == "no_relevant_module":
            if self._raw_end_invariant.evaluate(context["state"]):
                missing = self._missing_required_effects(context)
                if missing:
                    context["failure_reason"] = "unsatisfied_convergence_effects"

    def _checkpoint(self, context: Mapping[str, Any]) -> dict[str, Any]:
        checkpoint = super()._checkpoint(context)
        checkpoint.pop("checkpointHash", None)
        checkpoint["convergenceEffectPolicy"] = CONVERGENCE_EFFECT_POLICY
        checkpoint["requiredConvergenceEffects"] = list(
            self.spec.required_convergence_effects
        )
        checkpoint["realizedConvergenceEffects"] = self._realized_effects(context)
        checkpoint["convergenceEffectBlocks"] = deepcopy(
            list(context.get("convergence_effect_blocks", []))
        )
        checkpoint["checkpointHash"] = deterministic_hash(checkpoint)
        return checkpoint

    def _restore_checkpoint(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        if checkpoint.get("convergenceEffectPolicy") != CONVERGENCE_EFFECT_POLICY:
            raise ValueError("checkpoint convergence effect policy mismatch")
        if checkpoint.get("requiredConvergenceEffects") != list(
            self.spec.required_convergence_effects
        ):
            raise ValueError("checkpoint required convergence effects mismatch")
        context = super()._restore_checkpoint(checkpoint)
        context["convergence_effect_blocks"] = deepcopy(
            list(checkpoint.get("convergenceEffectBlocks", []))
        )
        expected_realized = self._realized_effects(context)
        if checkpoint.get("realizedConvergenceEffects") != expected_realized:
            raise ValueError("checkpoint realized convergence effects mismatch")
        return context

    def _receipt(self, context: Mapping[str, Any], *, commit: bool) -> dict[str, Any]:
        receipt = super()._receipt(context, commit=commit)
        receipt.pop("receiptHash", None)
        realized = self._realized_effects(context)
        missing = self._missing_required_effects(context)
        raw_end_passed = self._raw_end_invariant.evaluate(context["state"])
        effective_end_passed = bool(raw_end_passed and not missing)
        for result in receipt["invariantResults"]:
            if result["kind"] == "hard_end" and result["id"] == self._raw_end_invariant.invariant_id:
                result["passed"] = effective_end_passed

        receipt["convergenceEffectPolicy"] = CONVERGENCE_EFFECT_POLICY
        receipt["requiredConvergenceEffects"] = list(
            self.spec.required_convergence_effects
        )
        receipt["realizedConvergenceEffects"] = realized
        receipt["missingConvergenceEffects"] = missing
        receipt["rawEndInvariantPassed"] = raw_end_passed
        receipt["convergenceRequirementsPassed"] = effective_end_passed
        receipt["convergenceEffectBlocks"] = deepcopy(
            list(context.get("convergence_effect_blocks", []))
        )
        receipt["resourceUsage"]["realizedConvergenceEffectCount"] = len(realized)
        receipt["resourceUsage"]["missingConvergenceEffectCount"] = len(missing)
        receipt["receiptHash"] = deterministic_hash(receipt)
        return receipt

    def replay(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        replayed = super().replay(receipt)
        extra_keys = (
            "convergenceEffectPolicy",
            "requiredConvergenceEffects",
            "realizedConvergenceEffects",
            "missingConvergenceEffects",
            "rawEndInvariantPassed",
            "convergenceRequirementsPassed",
            "convergenceEffectBlocks",
        )
        replayed["replayMatches"] = bool(
            replayed["replayMatches"]
            and all(replayed.get(key) == receipt.get(key) for key in extra_keys)
        )
        return replayed


commit_receipt_to_history = _v07.commit_receipt_to_history
