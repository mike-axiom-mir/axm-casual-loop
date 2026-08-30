from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .engine import CausalLoopEngine, Invariant, LoopSpec, Module

LOOP_ID = "axm.train-platform-loop/v0.01"


def initial_state() -> dict[str, Any]:
    return {
        "train.status": "approaching",
        "train.departureDelay": 0,
        "door.state": "closed",
        "passenger.state": "waiting",
        "guard.state": "idle",
        "alarm.active": False,
        "platform.obstructed": False,
        "weather.snow": "none",
        "player.blockingDoor": False,
        "player.triggerAlarm": False,
        "player.talkingToPassenger": False,
        "delay.block": 0,
        "delay.alarm": 0,
        "flags.arrived": False,
        "flags.passengerApproached": False,
        "flags.doorOpened": False,
        "flags.obstructionObserved": False,
        "flags.alarmObserved": False,
        "flags.guardResolved": False,
        "flags.passengerBoarded": False,
        "flags.doorClosed": False,
    }


def intervention_handler(action: str, _state: Mapping[str, Any]) -> Mapping[str, Any]:
    if action == "WAIT":
        return {}
    if action == "BLOCK_DOOR":
        return {"player.blockingDoor": True}
    if action == "TRIGGER_ALARM":
        return {"player.triggerAlarm": True}
    if action == "TALK_TO_PASSENGER":
        return {"player.talkingToPassenger": True}
    raise ValueError(f"unsupported intervention: {action}")


def _modules() -> list[Module]:
    return [
        Module(
            "01-train-arrive",
            "0.01",
            ("train.status",),
            lambda s: s["train.status"] == "approaching",
            lambda _s: {"train.status": "arrived", "flags.arrived": True},
            authority_scope=("train.status", "flags.arrived"),
        ),
        Module(
            "02-door-open",
            "0.01",
            ("train.status", "door.state", "flags.doorOpened"),
            lambda s: s["train.status"] == "arrived" and s["door.state"] == "closed" and not s["flags.doorOpened"],
            lambda _s: {"door.state": "open", "flags.doorOpened": True},
            authority_scope=("door.state", "flags.doorOpened"),
        ),
        Module(
            "03-passenger-approach",
            "0.01",
            ("train.status", "passenger.state", "flags.passengerApproached"),
            lambda s: s["train.status"] == "arrived" and s["passenger.state"] == "waiting" and not s["flags.passengerApproached"],
            lambda _s: {"passenger.state": "at_door", "flags.passengerApproached": True},
            authority_scope=("passenger.state", "flags.passengerApproached"),
        ),
        Module(
            "04-obstruction",
            "0.01",
            ("door.state", "player.blockingDoor", "platform.obstructed", "flags.obstructionObserved"),
            lambda s: s["door.state"] == "open" and s["player.blockingDoor"] and not s["flags.obstructionObserved"],
            lambda _s: {"platform.obstructed": True, "flags.obstructionObserved": True},
            authority_scope=("platform.obstructed", "flags.obstructionObserved"),
        ),
        Module(
            "05-alarm-trigger",
            "0.01",
            ("player.triggerAlarm", "alarm.active", "flags.alarmObserved"),
            lambda s: s["player.triggerAlarm"] and not s["alarm.active"] and not s["flags.alarmObserved"],
            lambda _s: {"alarm.active": True, "flags.alarmObserved": True},
            authority_scope=("alarm.active", "flags.alarmObserved"),
        ),
        Module(
            "06-block-delay",
            "0.01",
            ("platform.obstructed", "delay.block"),
            lambda s: s["platform.obstructed"] and s["delay.block"] == 0,
            lambda _s: {"delay.block": 1},
            authority_scope=("delay.block",),
        ),
        Module(
            "07-alarm-delay",
            "0.01",
            ("alarm.active", "delay.alarm"),
            lambda s: s["alarm.active"] and s["delay.alarm"] == 0,
            lambda _s: {"delay.alarm": 2},
            authority_scope=("delay.alarm",),
        ),
        Module(
            "08-delay-derive",
            "0.01",
            ("delay.block", "delay.alarm", "train.departureDelay"),
            lambda s: s["train.departureDelay"] != s["delay.block"] + s["delay.alarm"],
            lambda s: {"train.departureDelay": s["delay.block"] + s["delay.alarm"]},
            authority_scope=("train.departureDelay",),
        ),
        Module(
            "09-guard-investigate",
            "0.01",
            ("platform.obstructed", "alarm.active", "guard.state", "flags.guardResolved"),
            lambda s: (s["platform.obstructed"] or s["alarm.active"]) and not s["flags.guardResolved"],
            lambda _s: {
                "guard.state": "resolved_incident",
                "platform.obstructed": False,
                "alarm.active": False,
                "player.blockingDoor": False,
                "player.triggerAlarm": False,
                "flags.guardResolved": True,
            },
            authority_scope=(
                "guard.state",
                "platform.obstructed",
                "alarm.active",
                "player.blockingDoor",
                "player.triggerAlarm",
                "flags.guardResolved",
            ),
        ),
        Module(
            "10-passenger-board",
            "0.01",
            (
                "door.state",
                "passenger.state",
                "platform.obstructed",
                "alarm.active",
                "player.blockingDoor",
                "player.triggerAlarm",
                "flags.passengerBoarded",
            ),
            lambda s: (
                s["door.state"] == "open"
                and s["passenger.state"] == "at_door"
                and not s["platform.obstructed"]
                and not s["alarm.active"]
                and not s["player.blockingDoor"]
                and not s["player.triggerAlarm"]
                and not s["flags.passengerBoarded"]
            ),
            lambda _s: {"passenger.state": "boarded", "flags.passengerBoarded": True},
            authority_scope=("passenger.state", "flags.passengerBoarded"),
        ),
        Module(
            "11-door-close",
            "0.01",
            ("door.state", "passenger.state", "platform.obstructed", "alarm.active", "flags.doorClosed"),
            lambda s: (
                s["door.state"] == "open"
                and s["passenger.state"] == "boarded"
                and not s["platform.obstructed"]
                and not s["alarm.active"]
                and not s["flags.doorClosed"]
            ),
            lambda _s: {"door.state": "closed", "flags.doorClosed": True},
            authority_scope=("door.state", "flags.doorClosed"),
        ),
        Module(
            "12-train-depart",
            "0.01",
            ("train.status", "door.state", "passenger.state", "alarm.active"),
            lambda s: s["train.status"] == "arrived" and s["door.state"] == "closed" and s["passenger.state"] == "boarded" and not s["alarm.active"],
            lambda _s: {"train.status": "departed"},
            authority_scope=("train.status",),
            convergence_effects=("train_departed",),
        ),
        Module(
            "99-unused-snow-module",
            "0.01",
            ("weather.snow",),
            lambda s: s["weather.snow"] == "heavy",
            lambda _s: {"platform.obstructed": True},
            authority_scope=("platform.obstructed",),
        ),
    ]


def build_engine(*, reverse_registry: bool = False, max_waves: int = 64) -> CausalLoopEngine:
    modules = _modules()
    if reverse_registry:
        modules.reverse()
    spec = LoopSpec(
        loop_id=LOOP_ID,
        version="0.01",
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
                lambda s: isinstance(s["train.departureDelay"], int) and s["train.departureDelay"] >= 0,
            ),
        ),
        soft_invariants=(
            Invariant("on_time_departure", lambda s: s["train.departureDelay"] == 0, "soft"),
        ),
        intervention_handler=intervention_handler,
        max_waves=max_waves,
    )
    return CausalLoopEngine(spec, modules)
