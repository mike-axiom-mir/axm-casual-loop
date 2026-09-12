from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .engine import deterministic_hash

ATLAS_SCHEMA = "axm.causal-loop.causal-atlas/v0.08"
VERIFICATION_SCHEMA = "axm.causal-loop.causal-atlas-verification/v0.01"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_TOP_LEVEL_KEYS = {
    "schema",
    "loopId",
    "loopVersion",
    "engineSignature",
    "moduleReadKeys",
    "summary",
    "deterministicMismatchCases",
    "pathGroups",
    "endStateGroups",
    "cases",
    "atlasHash",
}

_CASE_KEYS = {
    "caseId",
    "timedExternalInfluences",
    "status",
    "failureReason",
    "deterministicRepeat",
    "receiptHash",
    "realizedPathHash",
    "endStateHash",
    "causalDepth",
    "transitionCount",
    "moduleActivationCount",
    "contradictionCount",
    "authorityViolationCount",
    "readViolationCount",
    "hardInvariantFailures",
    "appliedTimedInfluences",
    "unappliedTimedInfluences",
    "orphanExternalWriteKeys",
    "unresolvedExternalWrites",
    "authorityViolations",
    "readViolations",
}

_SUMMARY_KEYS = {
    "caseCount",
    "convergedCount",
    "failedCount",
    "uniqueRealizedPathCount",
    "uniqueEndStateCount",
    "deterministicMismatchCount",
    "hardInvariantFailureCaseCount",
    "contradictionCaseCount",
    "authorityViolationCaseCount",
    "readViolationCaseCount",
    "orphanExternalWriteKeys",
    "unresolvedExternalWriteKeys",
    "failuresByReason",
}


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise ValueError(f"{name} keys do not match schema ({'; '.join(details)})")


def _require_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
    return value


def _require_nonnegative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_string_list(
    value: Any,
    name: str,
    *,
    sorted_unique: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must contain non-empty strings")
    if sorted_unique and value != sorted(set(value)):
        raise ValueError(f"{name} must be sorted and unique")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _validate_group_map(
    value: Any,
    name: str,
    *,
    known_case_ids: set[str],
) -> dict[str, list[str]]:
    mapping = _require_mapping(value, name)
    result: dict[str, list[str]] = {}
    for digest, case_ids in mapping.items():
        _require_sha256(digest, f"{name} key")
        ids = _require_string_list(case_ids, f"{name}[{digest}]")
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name}[{digest}] must not contain duplicate case IDs")
        unknown = sorted(set(ids) - known_case_ids)
        if unknown:
            raise ValueError(f"{name}[{digest}] references unknown case IDs: {', '.join(unknown)}")
        result[digest] = ids
    return result


def verify_atlas(
    atlas: Mapping[str, Any],
    *,
    expected_engine_signature: str | None = None,
    expected_loop_id: str | None = None,
    expected_loop_version: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless a saved Causal Atlas is internally consistent.

    This verifies deterministic artifact integrity plus the redundant summary/grouping
    relationships embedded in the v0.08 Atlas. It does not authenticate the producer
    and does not replay the underlying causal runs.
    """

    atlas = _require_mapping(atlas, "atlas")
    _require_exact_keys(atlas, _TOP_LEVEL_KEYS, "atlas")

    if atlas["schema"] != ATLAS_SCHEMA:
        raise ValueError(f"unsupported atlas schema: {atlas['schema']!r}")

    loop_id = _require_non_empty_string(atlas["loopId"], "loopId")
    loop_version = _require_non_empty_string(atlas["loopVersion"], "loopVersion")
    engine_signature = _require_sha256(atlas["engineSignature"], "engineSignature")
    atlas_hash = _require_sha256(atlas["atlasHash"], "atlasHash")

    if expected_loop_id is not None and loop_id != expected_loop_id:
        raise ValueError("atlas loopId does not match expected loop")
    if expected_loop_version is not None and loop_version != expected_loop_version:
        raise ValueError("atlas loopVersion does not match expected loop version")
    if expected_engine_signature is not None:
        _require_sha256(expected_engine_signature, "expected_engine_signature")
        if engine_signature != expected_engine_signature:
            raise ValueError("atlas engineSignature does not match expected engine")

    unsigned = deepcopy(dict(atlas))
    unsigned.pop("atlasHash")
    if deterministic_hash(unsigned) != atlas_hash:
        raise ValueError("atlasHash does not match the supplied atlas body")

    _require_string_list(atlas["moduleReadKeys"], "moduleReadKeys", sorted_unique=True)

    cases = _require_list(atlas["cases"], "cases")
    validated_cases: list[Mapping[str, Any]] = []
    case_ids: list[str] = []
    for index, raw_case in enumerate(cases):
        case = _require_mapping(raw_case, f"cases[{index}]")
        _require_exact_keys(case, _CASE_KEYS, f"cases[{index}]")
        case_id = _require_non_empty_string(case["caseId"], f"cases[{index}].caseId")
        if case_id in case_ids:
            raise ValueError(f"duplicate caseId: {case_id}")
        case_ids.append(case_id)

        _require_list(case["timedExternalInfluences"], f"cases[{index}].timedExternalInfluences")
        if case["status"] not in {"converged", "failed"}:
            raise ValueError(f"cases[{index}].status must be converged or failed")
        if case["failureReason"] is not None and (
            not isinstance(case["failureReason"], str) or not case["failureReason"]
        ):
            raise ValueError(f"cases[{index}].failureReason must be null or a non-empty string")
        if not isinstance(case["deterministicRepeat"], bool):
            raise ValueError(f"cases[{index}].deterministicRepeat must be boolean")

        for field in ("receiptHash", "realizedPathHash", "endStateHash"):
            _require_sha256(case[field], f"cases[{index}].{field}")
        for field in (
            "causalDepth",
            "transitionCount",
            "moduleActivationCount",
            "contradictionCount",
            "authorityViolationCount",
            "readViolationCount",
        ):
            _require_nonnegative_int(case[field], f"cases[{index}].{field}")

        _require_string_list(
            case["hardInvariantFailures"],
            f"cases[{index}].hardInvariantFailures",
            sorted_unique=True,
        )
        _require_list(case["appliedTimedInfluences"], f"cases[{index}].appliedTimedInfluences")
        _require_list(case["unappliedTimedInfluences"], f"cases[{index}].unappliedTimedInfluences")
        _require_string_list(
            case["orphanExternalWriteKeys"],
            f"cases[{index}].orphanExternalWriteKeys",
            sorted_unique=True,
        )
        unresolved = _require_list(
            case["unresolvedExternalWrites"],
            f"cases[{index}].unresolvedExternalWrites",
        )
        for unresolved_index, item in enumerate(unresolved):
            item = _require_mapping(
                item,
                f"cases[{index}].unresolvedExternalWrites[{unresolved_index}]",
            )
            _require_non_empty_string(
                item.get("key"),
                f"cases[{index}].unresolvedExternalWrites[{unresolved_index}].key",
            )

        authority_violations = _require_list(
            case["authorityViolations"],
            f"cases[{index}].authorityViolations",
        )
        read_violations = _require_list(
            case["readViolations"],
            f"cases[{index}].readViolations",
        )
        if case["authorityViolationCount"] != len(authority_violations):
            raise ValueError(f"cases[{index}].authorityViolationCount does not match evidence")
        if case["readViolationCount"] != len(read_violations):
            raise ValueError(f"cases[{index}].readViolationCount does not match evidence")

        validated_cases.append(case)

    known_case_ids = set(case_ids)
    mismatch_cases = _require_string_list(
        atlas["deterministicMismatchCases"],
        "deterministicMismatchCases",
    )
    expected_mismatch_cases = [
        case["caseId"] for case in validated_cases if not case["deterministicRepeat"]
    ]
    if mismatch_cases != expected_mismatch_cases:
        raise ValueError("deterministicMismatchCases does not match case evidence")

    path_groups = _validate_group_map(
        atlas["pathGroups"],
        "pathGroups",
        known_case_ids=known_case_ids,
    )
    end_state_groups = _validate_group_map(
        atlas["endStateGroups"],
        "endStateGroups",
        known_case_ids=known_case_ids,
    )

    expected_path_groups: dict[str, list[str]] = {}
    expected_end_state_groups: dict[str, list[str]] = {}
    for case in validated_cases:
        expected_path_groups.setdefault(case["realizedPathHash"], []).append(case["caseId"])
        expected_end_state_groups.setdefault(case["endStateHash"], []).append(case["caseId"])
    expected_path_groups = dict(sorted(expected_path_groups.items()))
    expected_end_state_groups = dict(sorted(expected_end_state_groups.items()))
    if path_groups != expected_path_groups:
        raise ValueError("pathGroups does not match case realizedPathHash evidence")
    if end_state_groups != expected_end_state_groups:
        raise ValueError("endStateGroups does not match case endStateHash evidence")

    failures_by_reason: dict[str, int] = {}
    orphan_write_keys: set[str] = set()
    unresolved_write_keys: set[str] = set()
    for case in validated_cases:
        if case["status"] == "failed":
            reason = case["failureReason"] or "unknown"
            failures_by_reason[reason] = failures_by_reason.get(reason, 0) + 1
        orphan_write_keys.update(case["orphanExternalWriteKeys"])
        unresolved_write_keys.update(
            item["key"] for item in case["unresolvedExternalWrites"]
        )

    expected_summary = {
        "caseCount": len(validated_cases),
        "convergedCount": sum(case["status"] == "converged" for case in validated_cases),
        "failedCount": sum(case["status"] == "failed" for case in validated_cases),
        "uniqueRealizedPathCount": len(expected_path_groups),
        "uniqueEndStateCount": len(expected_end_state_groups),
        "deterministicMismatchCount": len(expected_mismatch_cases),
        "hardInvariantFailureCaseCount": sum(
            bool(case["hardInvariantFailures"]) for case in validated_cases
        ),
        "contradictionCaseCount": sum(
            case["contradictionCount"] > 0 for case in validated_cases
        ),
        "authorityViolationCaseCount": sum(
            case["authorityViolationCount"] > 0 for case in validated_cases
        ),
        "readViolationCaseCount": sum(
            case["readViolationCount"] > 0 for case in validated_cases
        ),
        "orphanExternalWriteKeys": sorted(orphan_write_keys),
        "unresolvedExternalWriteKeys": sorted(unresolved_write_keys),
        "failuresByReason": dict(sorted(failures_by_reason.items())),
    }
    summary = _require_mapping(atlas["summary"], "summary")
    _require_exact_keys(summary, _SUMMARY_KEYS, "summary")
    if dict(summary) != expected_summary:
        raise ValueError("summary does not match case/group evidence")

    verification = {
        "schema": VERIFICATION_SCHEMA,
        "accepted": True,
        "atlasSchema": ATLAS_SCHEMA,
        "atlasHash": atlas_hash,
        "loopId": loop_id,
        "loopVersion": loop_version,
        "engineSignature": engine_signature,
        "caseCount": len(validated_cases),
        "uniqueRealizedPathCount": len(expected_path_groups),
        "uniqueEndStateCount": len(expected_end_state_groups),
    }
    verification["verificationHash"] = deterministic_hash(verification)
    return verification
