#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

REPOSITORY = "mike-axiom-mir/axm-casual-loop"
DISPLAY_NAME = "AXM Causal Loop Fabric"
DISCOVERY_BUDDY_REF = "565c38ecf93a9d563b02211258d8d36fcb1162b5"
PATTERN_REF = "2ac02c4ee0d17ea5772ae923aba522c2d3e9f297"

MARKER_PATH = ".axm/discovery-public.json"
DESCRIPTOR_PATH = "capabilities/causal-loop-process-v1.json"
ADAPTER_PATH = "causal_loop/process_adapter.py"
ENTRYPOINT_PATH = "scripts/causal_loop_ndjson.py"
LICENSE_PATH = "LICENSE"
REGISTRY_PATH = "registry/capabilities.jsonl"
RECEIPT_PATH = "registry/capabilities.receipt.json"

SOURCE_PATHS = (
    DESCRIPTOR_PATH,
    ADAPTER_PATH,
    ENTRYPOINT_PATH,
    LICENSE_PATH,
)
CAPABILITY_ID = "axm.causal-loop.train-platform.process/v1"
REQUEST_SCHEMA = "axm.causal-loop.process-request/v1"
RESPONSE_SCHEMA = "axm.causal-loop.process-response/v1"
RUN_RECEIPT_SCHEMA = "axm.causal-loop.run-receipt/v0.08"
EXPECTED_ACTIONS = ["WAIT", "BLOCK_DOOR", "TRIGGER_ALARM", "TALK_TO_PASSENGER"]
EXPECTED_AUTHORITY = {
    "commitsHistory": False,
    "writesCanonicalState": False,
    "merges": False,
    "declaresCanon": False,
}
EXPECTED_PROPERTIES = {
    "deterministic": True,
    "headless": True,
    "offline": True,
    "thirdPartyDependencies": False,
}


class DiscoveryError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DiscoveryError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise DiscoveryError(f"non-finite JSON number: {value}")


def strict_json_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DiscoveryError(str(exc)) from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def regular_file(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = root / relative_path
    try:
        info = candidate.lstat()
    except FileNotFoundError as exc:
        raise DiscoveryError(f"required source is missing: {relative_path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise DiscoveryError(f"source must be a regular non-symlink file: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except ValueError as exc:
        raise DiscoveryError(f"source path escapes repository root: {relative_path}") from exc
    return resolved


def read_json_file(root: Path, relative_path: str) -> Any:
    path = regular_file(root, relative_path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise DiscoveryError(f"source is not valid UTF-8: {relative_path}") from exc
    return strict_json_loads(text)


def source_record(root: Path, relative_path: str) -> dict[str, str]:
    data = regular_file(root, relative_path).read_bytes()
    return {"path": relative_path, "git_blob_sha1": git_blob_sha1(data)}


def validate_marker(root: Path) -> dict[str, Any]:
    marker = read_json_file(root, MARKER_PATH)
    expected = {
        "schema": "axm.discovery-public/v1",
        "public": True,
        "repo": REPOSITORY,
        "display_name": DISPLAY_NAME,
    }
    if marker != expected:
        raise DiscoveryError("public discovery marker drift")
    return marker


def validate_descriptor(descriptor: Any) -> dict[str, Any]:
    if not isinstance(descriptor, dict):
        raise DiscoveryError("capability descriptor must be a JSON object")
    expected_top = {"schema", "capabilityId", "provider", "protocol", "engine", "properties", "authority"}
    if set(descriptor) != expected_top:
        raise DiscoveryError("capability descriptor top-level shape drift")
    if descriptor.get("schema") != "axm.capability/v1":
        raise DiscoveryError("capability descriptor schema drift")
    if descriptor.get("capabilityId") != CAPABILITY_ID:
        raise DiscoveryError("capability id drift")

    provider = descriptor.get("provider")
    if provider != {
        "repository": REPOSITORY,
        "module": "causal_loop.process_adapter",
        "entrypoint": ENTRYPOINT_PATH,
        "licenseFile": LICENSE_PATH,
    }:
        raise DiscoveryError("provider boundary drift")

    protocol = descriptor.get("protocol")
    if protocol != {
        "transport": "ndjson-stdio",
        "requestSchema": REQUEST_SCHEMA,
        "responseSchema": RESPONSE_SCHEMA,
        "operations": ["describe", "run", "verify"],
    }:
        raise DiscoveryError("process protocol drift")

    engine = descriptor.get("engine")
    if not isinstance(engine, dict):
        raise DiscoveryError("engine descriptor missing")
    if set(engine) != {
        "loopId",
        "loopVersion",
        "receiptSchema",
        "engineSignature",
        "allowedActions",
        "maxTimedInfluences",
        "maxWavesLimit",
    }:
        raise DiscoveryError("engine descriptor shape drift")
    if engine.get("loopId") != "axm.train-platform-loop/v0.01":
        raise DiscoveryError("loop id drift")
    if engine.get("loopVersion") != "0.08":
        raise DiscoveryError("loop version drift")
    if engine.get("receiptSchema") != RUN_RECEIPT_SCHEMA:
        raise DiscoveryError("receipt schema drift")
    signature = engine.get("engineSignature")
    if not isinstance(signature, str) or len(signature) != 64 or any(ch not in "0123456789abcdef" for ch in signature):
        raise DiscoveryError("engine signature must be lowercase SHA-256")
    if engine.get("allowedActions") != EXPECTED_ACTIONS:
        raise DiscoveryError("allowed action contract drift")
    if engine.get("maxTimedInfluences") != 64 or engine.get("maxWavesLimit") != 256:
        raise DiscoveryError("process bound drift")

    if descriptor.get("properties") != EXPECTED_PROPERTIES:
        raise DiscoveryError("offline/deterministic property drift")
    if descriptor.get("authority") != EXPECTED_AUTHORITY:
        raise DiscoveryError("provider authority drift")
    if "status" in descriptor:
        raise DiscoveryError("provider maturity status appeared; review mapping before public export")
    return descriptor


def live_descriptor(root: Path) -> dict[str, Any]:
    entrypoint = regular_file(root, ENTRYPOINT_PATH)
    request = canonical_json(
        {"schema": REQUEST_SCHEMA, "requestId": "public-discovery", "op": "describe"}
    ) + "\n"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, str(entrypoint)],
            cwd=str(root.resolve()),
            input=request,
            text=True,
            capture_output=True,
            env=env,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoveryError(f"cannot execute capability describe boundary: {exc}") from exc
    if completed.returncode != 0:
        raise DiscoveryError(
            f"capability describe boundary failed with exit {completed.returncode}: {completed.stderr.strip()}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise DiscoveryError("capability describe boundary must emit exactly one response")
    response = strict_json_loads(lines[0])
    if not isinstance(response, dict):
        raise DiscoveryError("capability describe response must be an object")
    if response.get("schema") != RESPONSE_SCHEMA or response.get("status") != "PASS":
        raise DiscoveryError("capability describe response did not PASS")
    capability = response.get("capability")
    if not isinstance(capability, dict):
        raise DiscoveryError("capability describe response is missing capability")
    if response.get("capabilityId") != CAPABILITY_ID:
        raise DiscoveryError("capability describe response id drift")
    if response.get("authority") != capability.get("authority"):
        raise DiscoveryError("capability describe response authority drift")
    return capability


def build_artifacts(root: Path | str = Path.cwd()) -> dict[str, str]:
    root = Path(root)
    validate_marker(root)
    descriptor = validate_descriptor(read_json_file(root, DESCRIPTOR_PATH))
    observed = validate_descriptor(live_descriptor(root))
    if observed != descriptor:
        raise DiscoveryError("live capability descriptor does not match committed descriptor")

    sources = [source_record(root, relative_path) for relative_path in SOURCE_PATHS]
    engine = descriptor["engine"]
    record = {
        "schema": "axm.public-capability/v1",
        "id": descriptor["capabilityId"],
        "version": engine["loopVersion"],
        "status": None,
        "providers": [REPOSITORY],
        "consumers": [],
        "summary": "Offline deterministic NDJSON process adapter for the bounded Train Platform causal loop.",
        "license": "Apache-2.0",
        "runtime": {
            "language": "python",
            "dependencies": 0,
            "network": False,
            "account": False,
            "aiModel": False,
        },
        "entrypoints": {
            "command": descriptor["provider"]["entrypoint"],
            "transport": descriptor["protocol"]["transport"],
            "discoveryOperation": "describe",
        },
        "contracts": {
            "processRequest": descriptor["protocol"]["requestSchema"],
            "processResponse": descriptor["protocol"]["responseSchema"],
            "runReceipt": engine["receiptSchema"],
            "loopId": engine["loopId"],
            "loopVersion": engine["loopVersion"],
            "engineSignature": engine["engineSignature"],
        },
        "source": {
            "descriptor": DESCRIPTOR_PATH,
            "adapter": ADAPTER_PATH,
            "entrypoint": ENTRYPOINT_PATH,
            "license": LICENSE_PATH,
        },
        "authority": {
            "discoveryOnly": True,
            "execution": False,
            "automaticSelection": False,
            "automaticInstall": False,
            "historyMutation": False,
            "canonicalStateMutation": False,
            "merge": False,
            "canon": False,
        },
    }
    registry_text = canonical_json(record) + "\n"

    receipt_body = {
        "schema": "axm.public-capability-registry-receipt/v1",
        "repository": REPOSITORY,
        "registry": {
            "path": REGISTRY_PATH,
            "sha256": sha256_bytes(registry_text.encode("utf-8")),
            "capability_count": 1,
            "capability_ids": [descriptor["capabilityId"]],
        },
        "sources": sources,
        "compatibility": {
            "consumer": "mike-axiom-mir/axm-discovery-buddy",
            "pinned_ref": DISCOVERY_BUDDY_REF,
            "portable_boundary": "discovery-buddy.pyz",
            "marker_contract": "axm.discovery-public/v1",
            "registry_contract": "registry/*capabilit*.jsonl",
        },
        "pattern_provenance": {
            "adapted_from_repository": "mike-axiom-mir/axm-floor-born",
            "adapted_from_ref": PATTERN_REF,
            "adapted_paths": [
                ".axm/discovery-public.json",
                "tools/generate-public-capabilities.mjs",
                ".github/workflows/public-capability-discovery.yml",
            ],
            "copied_runtime_code": False,
        },
        "truth_boundary": {
            "source_backed": True,
            "public_export_intent": True,
            "runtime_proof": False,
            "execution_authority": False,
            "automatic_selection_authority": False,
            "automatic_install_authority": False,
            "history_mutation_authority": False,
            "canonical_state_mutation_authority": False,
            "merge_authority": False,
            "canon_authority": False,
        },
    }
    receipt = dict(receipt_body)
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt_body).encode("utf-8"))
    return {
        REGISTRY_PATH: registry_text,
        RECEIPT_PATH: json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
    }


def check_artifacts(root: Path | str = Path.cwd()) -> tuple[bool, list[str], dict[str, str]]:
    root = Path(root)
    expected = build_artifacts(root)
    mismatches: list[str] = []
    for relative_path, expected_text in expected.items():
        target = root / relative_path
        if target.is_symlink():
            raise DiscoveryError(f"generated output must not be a symlink: {relative_path}")
        try:
            actual = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            actual = None
        if actual != expected_text:
            mismatches.append(relative_path)
    return not mismatches, mismatches, expected


def write_artifacts(root: Path | str = Path.cwd()) -> dict[str, str]:
    root = Path(root)
    artifacts = build_artifacts(root)
    for relative_path, text in artifacts.items():
        target = root / relative_path
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file():
                raise DiscoveryError(f"generated output must be a regular file: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate source-backed public capability discovery evidence.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify committed generated artifacts without rewriting")
    mode.add_argument("--write", action="store_true", help="write generated artifacts")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args(argv)
    try:
        if args.check:
            ok, mismatches, _ = check_artifacts(args.root)
            if not ok:
                print("public capability registry is stale: " + ", ".join(mismatches), file=sys.stderr)
                return 1
            print("public capability registry: PASS")
            return 0
        artifacts = write_artifacts(args.root)
        print("public capability registry: wrote " + ", ".join(artifacts))
        return 0
    except (DiscoveryError, OSError) as exc:
        print(f"public capability registry: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
