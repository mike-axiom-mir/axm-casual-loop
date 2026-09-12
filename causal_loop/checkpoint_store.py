from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from .engine import deterministic_hash

STORE_RECEIPT_SCHEMA = "axm.causal-loop.checkpoint-store-receipt/v0.01"
STORE_AUTHORITY = "STORAGE_ONLY_NO_RESUME_NO_CANON"
DEFAULT_MAX_CHECKPOINT_BYTES = 1024 * 1024


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("checkpoint is not strict portable JSON") from exc
    return encoded.encode("utf-8")


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {token}")


class LocalCheckpointStore:
    """Content-addressed local persistence for admitted causal checkpoints.

    The store owns bytes, not causal truth. It never chooses a "latest" checkpoint,
    never calls ``resume()``, and never grants merge/CANON authority. Callers must name
    the exact checkpoint SHA-256 and then pass loaded bytes through the engine's normal
    checkpoint admission path before execution can continue.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_checkpoint_bytes: int = DEFAULT_MAX_CHECKPOINT_BYTES,
    ) -> None:
        if (
            not isinstance(max_checkpoint_bytes, int)
            or isinstance(max_checkpoint_bytes, bool)
            or max_checkpoint_bytes <= 0
        ):
            raise ValueError("max_checkpoint_bytes must be a positive integer")
        self.root = Path(root)
        self.max_checkpoint_bytes = max_checkpoint_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("checkpoint store root must be a real directory")

    def _path_for(self, checkpoint_id: str) -> Path:
        if not _is_sha256(checkpoint_id):
            raise ValueError("checkpoint id must be a lowercase SHA-256")
        return self.root / f"{checkpoint_id}.json"

    def _read_bounded(self, path: Path) -> bytes:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("checkpoint path must be a regular file")
        if metadata.st_size > self.max_checkpoint_bytes:
            raise ValueError("checkpoint bytes exceed configured storage bound")
        with path.open("rb") as handle:
            payload = handle.read(self.max_checkpoint_bytes + 1)
        if len(payload) > self.max_checkpoint_bytes:
            raise ValueError("checkpoint bytes exceed configured storage bound")
        return payload

    def _validated_bytes(self, checkpoint: Mapping[str, Any]) -> tuple[str, bytes]:
        if not isinstance(checkpoint, Mapping):
            raise ValueError("checkpoint must be a mapping")
        data = deepcopy(dict(checkpoint))
        checkpoint_id = data.get("checkpointHash")
        if not _is_sha256(checkpoint_id):
            raise ValueError("checkpoint id must be a lowercase SHA-256")

        unsigned = deepcopy(data)
        unsigned.pop("checkpointHash", None)
        if deterministic_hash(unsigned) != checkpoint_id:
            raise ValueError("checkpoint hash mismatch")

        payload = _strict_json_bytes(data)
        if len(payload) > self.max_checkpoint_bytes:
            raise ValueError("checkpoint bytes exceed configured storage bound")
        return checkpoint_id, payload

    def _sync_directory(self) -> bool:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        try:
            descriptor = os.open(self.root, flags)
        except OSError:
            return False
        try:
            os.fsync(descriptor)
        except OSError:
            return False
        finally:
            os.close(descriptor)
        return True

    def save(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        checkpoint_id, payload = self._validated_bytes(checkpoint)
        final_path = self._path_for(checkpoint_id)

        if final_path.exists() or final_path.is_symlink():
            existing = self._read_bounded(final_path)
            if existing != payload:
                raise ValueError("existing checkpoint bytes do not match requested checkpoint")
            return {
                "schema": STORE_RECEIPT_SCHEMA,
                "operation": "save",
                "checkpointHash": checkpoint_id,
                "byteCount": len(payload),
                "created": False,
                "fileFsync": None,
                "directoryFsync": None,
                "authority": STORE_AUTHORITY,
            }

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{checkpoint_id}.",
            suffix=".tmp",
            dir=self.root,
        )
        temporary_path = Path(temporary_name)
        created = False
        directory_synced: bool | None = None
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                os.link(temporary_path, final_path)
                created = True
            except FileExistsError:
                existing = self._read_bounded(final_path)
                if existing != payload:
                    raise ValueError(
                        "existing checkpoint bytes do not match requested checkpoint"
                    )
            except OSError as exc:
                raise RuntimeError(
                    "filesystem does not support create-only checkpoint publication"
                ) from exc

            if created:
                directory_synced = self._sync_directory()
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

        return {
            "schema": STORE_RECEIPT_SCHEMA,
            "operation": "save",
            "checkpointHash": checkpoint_id,
            "byteCount": len(payload),
            "created": created,
            "fileFsync": True if created else None,
            "directoryFsync": directory_synced,
            "authority": STORE_AUTHORITY,
        }

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        path = self._path_for(checkpoint_id)
        try:
            payload = self._read_bounded(path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"checkpoint not found: {checkpoint_id}") from exc

        try:
            text = payload.decode("utf-8")
            parsed = json.loads(text, parse_constant=_reject_nonfinite)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("checkpoint file is not valid strict portable JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("checkpoint file must contain one JSON object")

        canonical = _strict_json_bytes(parsed)
        if canonical != payload:
            raise ValueError("canonical checkpoint bytes mismatch")
        if parsed.get("checkpointHash") != checkpoint_id:
            raise ValueError("checkpoint id does not match stored checkpoint")

        unsigned = deepcopy(parsed)
        unsigned.pop("checkpointHash", None)
        if deterministic_hash(unsigned) != checkpoint_id:
            raise ValueError("checkpoint hash mismatch")
        return deepcopy(parsed)
