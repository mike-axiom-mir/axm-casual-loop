from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations, combinations_with_replacement
from typing import Any, Iterable, Mapping, Sequence

from .engine import CausalLoopEngine, TimedInfluence, deterministic_hash


@dataclass(frozen=True)
class ExplorationCase:
    case_id: str
    timed_influences: tuple[TimedInfluence, ...]

    def contract(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "timedExternalInfluences": [
                influence.contract(sequence=index)
                for index, influence in enumerate(self.timed_influences)
            ],
        }


def bounded_schedule_cases(
    actions: Sequence[str],
    waves: Iterable[int],
    *,
    max_actions_per_case: int = 2,
    include_empty: bool = True,
    include_same_wave_reverse_order: bool = True,
    include_repeated_actions: bool = True,
) -> list[ExplorationCase]:
    """Generate a small deterministic schedule space for architecture probing.

    This deliberately does not pretend to enumerate every possible world. It creates a
    bounded, reproducible set of zero-, one-, and two-action schedules so hidden timing,
    ordering, repeated-action, dangling-direction, and convergence problems become
    measurable.
    """

    ordered_actions = tuple(dict.fromkeys(actions))
    ordered_waves = tuple(sorted(set(waves)))
    if not ordered_actions:
        raise ValueError("actions must not be empty")
    if not ordered_waves or any(
        not isinstance(wave, int) or isinstance(wave, bool) or wave < 0
        for wave in ordered_waves
    ):
        raise ValueError("waves must contain non-negative integers")
    if max_actions_per_case not in {1, 2}:
        raise ValueError("bounded explorer currently supports max_actions_per_case 1 or 2")

    cases: list[ExplorationCase] = []
    if include_empty:
        cases.append(ExplorationCase("empty", ()))

    for action in ordered_actions:
        for wave in ordered_waves:
            cases.append(
                ExplorationCase(
                    f"single:{action}@{wave}",
                    (TimedInfluence(wave, action),),
                )
            )

    if max_actions_per_case >= 2:
        for first, second in combinations(ordered_actions, 2):
            for first_wave in ordered_waves:
                for second_wave in ordered_waves:
                    cases.append(
                        ExplorationCase(
                            f"pair:{first}@{first_wave}+{second}@{second_wave}",
                            (
                                TimedInfluence(first_wave, first),
                                TimedInfluence(second_wave, second),
                            ),
                        )
                    )
                    if include_same_wave_reverse_order and first_wave == second_wave:
                        cases.append(
                            ExplorationCase(
                                f"pair-reversed:{second}@{second_wave}+{first}@{first_wave}",
                                (
                                    TimedInfluence(second_wave, second),
                                    TimedInfluence(first_wave, first),
                                ),
                            )
                        )

        if include_repeated_actions:
            for action in ordered_actions:
                for first_wave, second_wave in combinations_with_replacement(ordered_waves, 2):
                    cases.append(
                        ExplorationCase(
                            f"pair-repeat:{action}@{first_wave}+{action}@{second_wave}",
                            (
                                TimedInfluence(first_wave, action),
                                TimedInfluence(second_wave, action),
                            ),
                        )
                    )
    return cases


def _realized_path_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": receipt["status"],
        "failureReason": receipt["failureReason"],
        "appliedTimedInfluences": receipt["appliedTimedInfluences"],
        "modulesActivated": receipt["modulesActivated"],
        "stateTransitions": receipt["stateTransitions"],
        "contradictions": receipt["contradictions"],
        "endStateHash": receipt["endStateHash"],
        "invariantResults": receipt["invariantResults"],
    }


def _unresolved_external_writes(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Report external writes that survive to the endpoint without a later overwrite.

    This is diagnostic, not automatically an error: some architectures intentionally allow
    persistent external state. For the train proof it is useful for spotting transient
    direction flags that accidentally remain true after convergence or failure.
    """

    transitions = list(receipt["stateTransitions"])
    unresolved: list[dict[str, Any]] = []
    for index, transition in enumerate(transitions):
        if transition.get("kind") != "external":
            continue
        for key, value in transition.get("writes", {}).items():
            overwritten = any(
                key in later.get("writes", {}) for later in transitions[index + 1 :]
            )
            if not overwritten and receipt["endState"].get(key) == value:
                unresolved.append(
                    {
                        "wave": transition.get("wave"),
                        "sequence": transition.get("sequence"),
                        "action": transition.get("source"),
                        "key": key,
                        "value": value,
                    }
                )
    return unresolved


def explore_schedule_space(
    engine: CausalLoopEngine,
    initial_state: Mapping[str, Any],
    cases: Sequence[ExplorationCase],
    *,
    repeats: int = 2,
) -> dict[str, Any]:
    if repeats < 2:
        raise ValueError("repeats must be >= 2 so determinism is actually checked")

    module_read_keys = sorted({key for module in engine.modules for key in module.reads})
    module_read_key_set = set(module_read_keys)
    results: list[dict[str, Any]] = []
    deterministic_mismatches: list[str] = []
    orphan_write_keys: set[str] = set()
    unresolved_write_keys: set[str] = set()

    for case in cases:
        receipts = [
            engine.run(deepcopy(dict(initial_state)), timed_influences=case.timed_influences)
            for _ in range(repeats)
        ]
        first = receipts[0]
        repeat_hashes = [receipt["receiptHash"] for receipt in receipts]
        deterministic_repeat = len(set(repeat_hashes)) == 1
        if not deterministic_repeat:
            deterministic_mismatches.append(case.case_id)

        realized_path_hash = deterministic_hash(_realized_path_payload(first))
        applied_external_write_keys = sorted(
            {
                key
                for item in first["appliedTimedInfluences"]
                for key in item.get("writes", {})
            }
        )
        orphan_keys = sorted(
            key for key in applied_external_write_keys if key not in module_read_key_set
        )
        orphan_write_keys.update(orphan_keys)

        unresolved = _unresolved_external_writes(first)
        unresolved_keys = sorted({item["key"] for item in unresolved})
        unresolved_write_keys.update(unresolved_keys)

        hard_failures = sorted(
            result["id"]
            for result in first["invariantResults"]
            if result["kind"] in {"hard", "hard_end"} and not result["passed"]
        )
        results.append(
            {
                **case.contract(),
                "status": first["status"],
                "failureReason": first["failureReason"],
                "deterministicRepeat": deterministic_repeat,
                "receiptHash": first["receiptHash"],
                "realizedPathHash": realized_path_hash,
                "endStateHash": first["endStateHash"],
                "causalDepth": first["resourceUsage"]["causalDepth"],
                "transitionCount": first["resourceUsage"]["stateTransitions"],
                "moduleActivationCount": first["resourceUsage"]["moduleActivations"],
                "contradictionCount": first["resourceUsage"]["contradictionCount"],
                "hardInvariantFailures": hard_failures,
                "appliedTimedInfluences": first["appliedTimedInfluences"],
                "unappliedTimedInfluences": first["unappliedTimedInfluences"],
                "orphanExternalWriteKeys": orphan_keys,
                "unresolvedExternalWrites": unresolved,
            }
        )

    failures_by_reason: dict[str, int] = {}
    for result in results:
        if result["status"] == "failed":
            reason = result["failureReason"] or "unknown"
            failures_by_reason[reason] = failures_by_reason.get(reason, 0) + 1

    path_groups: dict[str, list[str]] = {}
    end_state_groups: dict[str, list[str]] = {}
    for result in results:
        path_groups.setdefault(result["realizedPathHash"], []).append(result["caseId"])
        end_state_groups.setdefault(result["endStateHash"], []).append(result["caseId"])

    atlas = {
        "schema": "axm.causal-loop.causal-atlas/v0.06",
        "loopId": engine.spec.loop_id,
        "loopVersion": engine.spec.version,
        "engineSignature": engine.engine_signature,
        "moduleReadKeys": module_read_keys,
        "summary": {
            "caseCount": len(results),
            "convergedCount": sum(result["status"] == "converged" for result in results),
            "failedCount": sum(result["status"] == "failed" for result in results),
            "uniqueRealizedPathCount": len(path_groups),
            "uniqueEndStateCount": len(end_state_groups),
            "deterministicMismatchCount": len(deterministic_mismatches),
            "hardInvariantFailureCaseCount": sum(
                bool(result["hardInvariantFailures"]) for result in results
            ),
            "contradictionCaseCount": sum(
                result["contradictionCount"] > 0 for result in results
            ),
            "orphanExternalWriteKeys": sorted(orphan_write_keys),
            "unresolvedExternalWriteKeys": sorted(unresolved_write_keys),
            "failuresByReason": dict(sorted(failures_by_reason.items())),
        },
        "deterministicMismatchCases": deterministic_mismatches,
        "pathGroups": {key: value for key, value in sorted(path_groups.items())},
        "endStateGroups": {key: value for key, value in sorted(end_state_groups.items())},
        "cases": results,
    }
    atlas["atlasHash"] = deterministic_hash(atlas)
    return atlas
