#!/usr/bin/env python3
"""Build and verify a deterministic one-file Causal Loop process provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_ID = "axm.causal-loop.train-platform.process/v1"
PORTABLE_SCHEMA = "axm.causal-loop.portable-process/v1"
VERIFY_SCHEMA = "axm.causal-loop.portable-process-verification/v1"
METADATA_NAME = "AXM_PORTABLE.json"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
SOURCE_PATHS = {
    "LICENSE": ROOT / "LICENSE",
    "capabilities/causal-loop-process-v1.json": ROOT / "capabilities/causal-loop-process-v1.json",
    "causal_loop/__init__.py": ROOT / "causal_loop/__init__.py",
    "causal_loop/engine.py": ROOT / "causal_loop/engine.py",
    "causal_loop/observer.py": ROOT / "causal_loop/observer.py",
    "causal_loop/process_adapter.py": ROOT / "causal_loop/process_adapter.py",
    "causal_loop/train_platform.py": ROOT / "causal_loop/train_platform.py",
}
AUTHORITY = {
    "automaticExecution": False,
    "automaticSelection": False,
    "installation": False,
    "commitsHistory": False,
    "writesCanonicalState": False,
    "merge": False,
    "canon": False,
}
PATTERN_PROVENANCE = {
    "repository": "mike-axiom-mir/axm-state-research",
    "pullRequest": 22,
    "sourceHead": "ec159470bef52974dad25292ea7a6b34be54ccd4",
    "relationship": "deterministic-zipapp-pattern-adapted-no-runtime-code-imported",
}
RUNTIME = {"python": ">=3.11", "networkRequired": False, "thirdPartyDependencies": False}
TRUTH_BOUNDARY = {
    "selfVerificationAuthenticatesProducer": False,
    "providerVerificationBindsTrustedCheckout": True,
    "portableArtifactExecutesOnlyWhenCallerInvokesIt": True,
    "processReceiptsRemainUncommitted": True,
}

WRAPPER = r"""from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys
import zipfile


CAPABILITY_ID = "axm.causal-loop.train-platform.process/v1"
PORTABLE_SCHEMA = "axm.causal-loop.portable-process/v1"
VERIFY_SCHEMA = "axm.causal-loop.portable-process-verification/v1"
METADATA_NAME = "AXM_PORTABLE.json"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
ALLOWED_NAMES = (
    "AXM_PORTABLE.json",
    "LICENSE",
    "__main__.py",
    "capabilities/causal-loop-process-v1.json",
    "causal_loop/__init__.py",
    "causal_loop/engine.py",
    "causal_loop/observer.py",
    "causal_loop/process_adapter.py",
    "causal_loop/train_platform.py",
)
AUTHORITY = {
    "automaticExecution": False,
    "automaticSelection": False,
    "installation": False,
    "commitsHistory": False,
    "writesCanonicalState": False,
    "merge": False,
    "canon": False,
}
PATTERN_PROVENANCE = {
    "repository": "mike-axiom-mir/axm-state-research",
    "pullRequest": 22,
    "sourceHead": "ec159470bef52974dad25292ea7a6b34be54ccd4",
    "relationship": "deterministic-zipapp-pattern-adapted-no-runtime-code-imported",
}
RUNTIME = {"python": ">=3.11", "networkRequired": False, "thirdPartyDependencies": False}
TRUTH_BOUNDARY = {
    "selfVerificationAuthenticatesProducer": False,
    "providerVerificationBindsTrustedCheckout": True,
    "portableArtifactExecutesOnlyWhenCallerInvokesIt": True,
    "processReceiptsRemainUncommitted": True,
}


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member: " + key)
        value[key] = item
    return value


def strict_json(data):
    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=strict_object,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON number: " + value)),
    )


def archive_path():
    return Path(sys.argv[0]).absolute()


def inspect_self():
    path = archive_path()
    if path.is_symlink() or not path.is_file():
        raise ValueError("portable artifact must be a regular non-symlink file")
    raw = path.read_bytes()
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("portable artifact exceeds size ceiling")
    payloads = {}
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")
        if tuple(sorted(names)) != ALLOWED_NAMES:
            raise ValueError("unexpected archive member set")
        total = 0
        for info in infos:
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("compressed member is outside the portable contract")
            if info.date_time != FIXED_DATE or info.create_system != 3:
                raise ValueError("archive metadata drift")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) != stat.S_IFREG or stat.S_IMODE(mode) != 0o644:
                raise ValueError("archive mode drift")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("archive member exceeds size ceiling")
            total += info.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("archive payload exceeds size ceiling")
            payloads[info.filename] = archive.read(info)
    metadata = strict_json(payloads[METADATA_NAME])
    if metadata.get("schema") != PORTABLE_SCHEMA:
        raise ValueError("portable schema mismatch")
    if metadata.get("capabilityId") != CAPABILITY_ID:
        raise ValueError("capability identity mismatch")
    if set(metadata) != {"schema", "capabilityId", "runtime", "processDescriptorSha256", "members", "patternProvenance", "authority", "truthBoundary"}:
        raise ValueError("portable metadata shape mismatch")
    if metadata.get("authority") != AUTHORITY:
        raise ValueError("authority drift")
    if metadata.get("runtime") != RUNTIME:
        raise ValueError("runtime contract drift")
    if metadata.get("patternProvenance") != PATTERN_PROVENANCE:
        raise ValueError("pattern provenance drift")
    if metadata.get("truthBoundary") != TRUTH_BOUNDARY:
        raise ValueError("truth boundary drift")
    members = metadata.get("members")
    if not isinstance(members, dict):
        raise ValueError("missing member evidence")
    expected_names = set(ALLOWED_NAMES) - {METADATA_NAME}
    if set(members) != expected_names:
        raise ValueError("member evidence set mismatch")
    for name, expected in members.items():
        body = payloads[name]
        if expected != {"bytes": len(body), "sha256": sha256_bytes(body)}:
            raise ValueError("member evidence mismatch: " + name)
    descriptor = strict_json(payloads["capabilities/causal-loop-process-v1.json"])
    if descriptor.get("capabilityId") != CAPABILITY_ID:
        raise ValueError("embedded process descriptor mismatch")
    if metadata.get("processDescriptorSha256") != sha256_bytes(payloads["capabilities/causal-loop-process-v1.json"]):
        raise ValueError("process descriptor evidence mismatch")
    return metadata, payloads, sha256_bytes(raw)


def hold(error):
    return {
        "schema": VERIFY_SCHEMA,
        "status": "HOLD",
        "error": str(error),
        "authority": AUTHORITY,
    }


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    try:
        metadata, payloads, archive_sha = inspect_self()
        if command == "portable-verify":
            sys.stdout.buffer.write(canonical_bytes({
                "schema": VERIFY_SCHEMA,
                "status": "PASS",
                "artifactSha256": archive_sha,
                "capabilityId": CAPABILITY_ID,
                "authority": AUTHORITY,
                "truthBoundary": metadata["truthBoundary"],
            }))
            return 0
        if command == "portable-describe":
            sys.stdout.buffer.write(canonical_bytes(metadata))
            return 0
        if command != "serve" or len(sys.argv) > 1:
            raise ValueError("portable command must be portable-verify, portable-describe, or no argument")
        descriptor = strict_json(payloads["capabilities/causal-loop-process-v1.json"])
        from causal_loop.process_adapter import capability_descriptor, main as process_main
        if capability_descriptor() != descriptor:
            raise ValueError("embedded live process contract differs from embedded descriptor")
        return process_main([], stdin=sys.stdin, stdout=sys.stdout)
    except (OSError, ValueError, KeyError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        sys.stderr.buffer.write(canonical_bytes(hold(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
"""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def strict_json_bytes(data: bytes) -> Any:
    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {value}")),
    )


def _source_payloads() -> dict[str, bytes]:
    payloads = {"__main__.py": WRAPPER.encode("utf-8")}
    for name, path in SOURCE_PATHS.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"provider source must be a regular non-symlink file: {path}")
        payloads[name] = path.read_bytes()
    descriptor = strict_json_bytes(payloads["capabilities/causal-loop-process-v1.json"])
    if descriptor.get("capabilityId") != CAPABILITY_ID:
        raise ValueError("provider descriptor capability identity mismatch")
    return payloads


def _metadata(payloads: dict[str, bytes]) -> dict[str, Any]:
    return {
        "schema": PORTABLE_SCHEMA,
        "capabilityId": CAPABILITY_ID,
        "runtime": RUNTIME,
        "processDescriptorSha256": sha256_bytes(payloads["capabilities/causal-loop-process-v1.json"]),
        "members": {
            name: {"bytes": len(body), "sha256": sha256_bytes(body)}
            for name, body in sorted(payloads.items())
        },
        "patternProvenance": PATTERN_PROVENANCE,
        "authority": AUTHORITY,
        "truthBoundary": TRUTH_BOUNDARY,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_DATE)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def build_archive(output: Path) -> dict[str, Any]:
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payloads = _source_payloads()
    payloads[METADATA_NAME] = canonical_bytes(_metadata(payloads))
    allowed = tuple(sorted(payloads))
    if any(len(body) > MAX_MEMBER_BYTES for body in payloads.values()):
        raise ValueError("provider member exceeds portable size ceiling")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w") as archive:
            for name in allowed:
                archive.writestr(_zip_info(name), payloads[name])
        raw = tmp.read_bytes()
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ValueError("portable artifact exceeds size ceiling")
        os.link(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    verified = verify_archive(output)
    return {
        "schema": PORTABLE_SCHEMA,
        "status": "PASS",
        "artifactSha256": verified["artifactSha256"],
        "artifactBytes": output.stat().st_size,
        "capabilityId": CAPABILITY_ID,
        "providerSourceBound": True,
        "authority": AUTHORITY,
    }


def _read_archive(path: Path) -> tuple[dict[str, Any], dict[str, bytes], str]:
    path = path.absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError("portable artifact must be a regular non-symlink file")
    raw = path.read_bytes()
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("portable artifact exceeds size ceiling")
    payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        expected_names = tuple(sorted((METADATA_NAME, "__main__.py", *SOURCE_PATHS.keys())))
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")
        if tuple(sorted(names)) != expected_names:
            raise ValueError("unexpected archive member set")
        total = 0
        for info in infos:
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("compressed member is outside the portable contract")
            if info.date_time != FIXED_DATE or info.create_system != 3:
                raise ValueError("archive metadata drift")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) != stat.S_IFREG or stat.S_IMODE(mode) != 0o644:
                raise ValueError("archive mode drift")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("archive member exceeds size ceiling")
            total += info.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("archive payload exceeds size ceiling")
            payloads[info.filename] = archive.read(info)
    metadata = strict_json_bytes(payloads[METADATA_NAME])
    if metadata.get("schema") != PORTABLE_SCHEMA or metadata.get("capabilityId") != CAPABILITY_ID:
        raise ValueError("portable identity mismatch")
    if set(metadata) != {"schema", "capabilityId", "runtime", "processDescriptorSha256", "members", "patternProvenance", "authority", "truthBoundary"}:
        raise ValueError("portable metadata shape mismatch")
    if metadata.get("authority") != AUTHORITY:
        raise ValueError("portable authority drift")
    if metadata.get("runtime") != RUNTIME:
        raise ValueError("portable runtime contract drift")
    if metadata.get("patternProvenance") != PATTERN_PROVENANCE:
        raise ValueError("portable pattern provenance drift")
    if metadata.get("truthBoundary") != TRUTH_BOUNDARY:
        raise ValueError("portable truth boundary drift")
    members = metadata.get("members")
    if not isinstance(members, dict) or set(members) != set(payloads) - {METADATA_NAME}:
        raise ValueError("member evidence set mismatch")
    for name, expected in members.items():
        body = payloads[name]
        if expected != {"bytes": len(body), "sha256": sha256_bytes(body)}:
            raise ValueError(f"member evidence mismatch: {name}")
    if metadata.get("processDescriptorSha256") != sha256_bytes(payloads["capabilities/causal-loop-process-v1.json"]):
        raise ValueError("process descriptor evidence mismatch")
    return metadata, payloads, sha256_bytes(raw)


def verify_archive(path: Path) -> dict[str, Any]:
    metadata, payloads, artifact_sha = _read_archive(path)
    trusted = _source_payloads()
    if set(trusted) != set(payloads) - {METADATA_NAME}:
        raise ValueError("provider source set mismatch")
    for name, expected in trusted.items():
        if payloads[name] != expected:
            raise ValueError(f"provider source mismatch: {name}")
    return {
        "schema": VERIFY_SCHEMA,
        "status": "PASS",
        "artifactSha256": artifact_sha,
        "capabilityId": CAPABILITY_ID,
        "providerSourceBound": True,
        "processDescriptorSha256": metadata["processDescriptorSha256"],
        "patternProvenance": metadata["patternProvenance"],
        "authority": AUTHORITY,
        "truthBoundary": metadata["truthBoundary"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the portable AXM Causal Loop process provider.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("artifact", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_archive(args.output) if args.command == "build" else verify_archive(args.artifact)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (OSError, ValueError, KeyError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        sys.stderr.buffer.write(canonical_bytes({
            "schema": VERIFY_SCHEMA,
            "status": "HOLD",
            "error": str(exc),
            "authority": AUTHORITY,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
