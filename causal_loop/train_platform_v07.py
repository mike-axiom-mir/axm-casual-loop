from __future__ import annotations

from dataclasses import replace

from . import train_platform_legacy as _legacy
from .engine import CausalLoopEngine, Invariant, LoopSpec

LOOP_ID = _legacy.LOOP_ID
initial_state = _legacy.initial_state
intervention_handler = _legacy.intervention_handler

INTERVENTION_WRITE_SCOPE = (
    "player.blockingDoor",
    "player.triggerAlarm",
    "player.talkingToPassenger",
)

MODULE_DEPENDENCIES = {
    "02-door-open": ("01-train-arrive",),
    "03-passenger-approach": ("01-train-arrive",),
    "04-obstruction": ("02-door-open",),
    "06-block-delay": ("04-obstruction",),
    "07-alarm-delay": ("05-alarm-trigger",),
    "10-passenger-board": ("03-passenger-approach",),
    "11-door-close": ("10-passenger-board",),
    "12-train-depart": ("11-door-close",),
}


def _modules_with_dependencies():
    return [
        replace(
            module,
            dependencies=MODULE_DEPENDENCIES.get(module.module_id, module.dependencies),
        )
        for module in _legacy._modules()
    ]


def build_engine(*, reverse_registry: bool = False, max_waves: int = 64) -> CausalLoopEngine:
    modules = _modules_with_dependencies()
    if reverse_registry:
        modules.reverse()
    spec = LoopSpec(
        loop_id=LOOP_ID,
        version="0.07",
        start_invariant=Invariant(
            "train_approaches_station",
            lambda s: s["train.status"] == "approaching",
            "start",
        ),
        end_invariant=Invariant(
            "train_eventually_leaves",
            lambda s: s["train.status"] == "departed",
            "hard_end",
        ),
        hard_invariants=(
            Invariant(
                "known_train_state",
                lambda s: s["train.status"] in {"approaching", "arrived", "departed"},
            ),
            Invariant(
                "nonnegative_delay",
                lambda s: isinstance(s["train.departureDelay"], int)
                and s["train.departureDelay"] >= 0,
            ),
            Invariant("departure_has_no_causal_debt", _legacy._departure_has_no_causal_debt),
        ),
        soft_invariants=(
            Invariant(
                "on_time_departure",
                lambda s: s["train.departureDelay"] == 0,
                "soft",
            ),
        ),
        intervention_handler=intervention_handler,
        max_waves=max_waves,
        receipt_schema="axm.causal-loop.run-receipt/v0.07",
        intervention_write_scope=INTERVENTION_WRITE_SCOPE,
    )
    return CausalLoopEngine(spec, modules)
