import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.build_causal_loop_portable import (
    AUTHORITY,
    build_archive,
    verify_archive,
)


ROOT = Path(__file__).resolve().parents[1]


class PortableProcessTests(unittest.TestCase):
    def build(self, directory: Path, name: str = "causal-loop-process.pyz") -> Path:
        output = directory / name
        receipt = build_archive(output)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["providerSourceBound"])
        return output

    def test_same_source_builds_are_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            first = self.build(directory, "first.pyz")
            second = self.build(directory, "second.pyz")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_provider_verification_binds_exact_checkout_sources(self):
        with tempfile.TemporaryDirectory() as raw:
            artifact = self.build(Path(raw))
            receipt = verify_archive(artifact)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["providerSourceBound"])
        self.assertEqual(receipt["authority"], AUTHORITY)
        self.assertEqual(
            receipt["patternProvenance"]["sourceHead"],
            "ec159470bef52974dad25292ea7a6b34be54ccd4",
        )

    def test_checkout_independent_process_is_byte_equal_to_source_adapter(self):
        request_bytes = (ROOT / "examples/process-requests.ndjson").read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            artifact = self.build(directory)
            consumer = directory / "consumer"
            consumer.mkdir()
            copied = consumer / artifact.name
            copied.write_bytes(artifact.read_bytes())
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            direct = subprocess.run(
                [sys.executable, str(ROOT / "scripts/causal_loop_ndjson.py")],
                cwd=consumer,
                input=request_bytes,
                capture_output=True,
                check=False,
                env=env,
            )
            portable = subprocess.run(
                [sys.executable, str(copied)],
                cwd=consumer,
                input=request_bytes,
                capture_output=True,
                check=False,
                env=env,
            )
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(portable.returncode, 0, portable.stderr)
        self.assertEqual(portable.stderr, b"")
        self.assertEqual(portable.stdout, direct.stdout)

    def test_standalone_verification_and_description_need_no_checkout_path(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            artifact = self.build(directory)
            consumer = directory / "consumer"
            consumer.mkdir()
            copied = consumer / artifact.name
            copied.write_bytes(artifact.read_bytes())
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            verified = subprocess.run(
                [sys.executable, str(copied), "portable-verify"],
                cwd=consumer,
                capture_output=True,
                check=False,
                env=env,
            )
            described = subprocess.run(
                [sys.executable, str(copied), "portable-describe"],
                cwd=consumer,
                capture_output=True,
                check=False,
                env=env,
            )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(described.returncode, 0, described.stderr)
        verify_receipt = json.loads(verified.stdout)
        metadata = json.loads(described.stdout)
        self.assertEqual(verify_receipt["status"], "PASS")
        self.assertEqual(metadata["capabilityId"], "axm.causal-loop.train-platform.process/v1")
        self.assertFalse(metadata["authority"]["automaticExecution"])
        self.assertFalse(metadata["authority"]["canon"])

    def test_tampered_member_fails_provider_and_self_verification(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            artifact = self.build(directory)
            tampered = directory / "tampered.pyz"
            with zipfile.ZipFile(artifact, "r") as source, zipfile.ZipFile(tampered, "w") as target:
                for info in source.infolist():
                    body = source.read(info)
                    if info.filename == "causal_loop/train_platform.py":
                        body += b"\n# tampered\n"
                    target.writestr(info, body)
            with self.assertRaisesRegex(ValueError, "member evidence mismatch"):
                verify_archive(tampered)
            held = subprocess.run(
                [sys.executable, str(tampered), "portable-verify"],
                capture_output=True,
                check=False,
            )
        self.assertEqual(held.returncode, 2)
        self.assertEqual(json.loads(held.stderr)["status"], "HOLD")

    def test_unexpected_archive_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            artifact = self.build(directory)
            changed = directory / "unexpected.pyz"
            changed.write_bytes(artifact.read_bytes())
            with zipfile.ZipFile(changed, "a", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("unexpected.txt", "not allowed")
            with self.assertRaisesRegex(ValueError, "unexpected archive member set"):
                verify_archive(changed)


if __name__ == "__main__":
    unittest.main()
