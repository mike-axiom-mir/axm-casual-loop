from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate_public_capabilities.py"

_spec = importlib.util.spec_from_file_location("generate_public_capabilities", GENERATOR_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load public capability generator")
generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generator)


def copy_fixture(destination: Path) -> None:
    (destination / ".axm").mkdir(parents=True)
    (destination / "capabilities").mkdir(parents=True)
    (destination / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / ".axm" / "discovery-public.json", destination / ".axm" / "discovery-public.json")
    shutil.copy2(
        ROOT / "capabilities" / "causal-loop-process-v1.json",
        destination / "capabilities" / "causal-loop-process-v1.json",
    )
    shutil.copytree(ROOT / "causal_loop", destination / "causal_loop")
    shutil.copy2(
        ROOT / "scripts" / "causal_loop_ndjson.py",
        destination / "scripts" / "causal_loop_ndjson.py",
    )
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")


class PublicCapabilityDiscoveryTests(unittest.TestCase):
    def test_committed_generated_artifacts_are_exact(self) -> None:
        ok, mismatches, artifacts = generator.check_artifacts(ROOT)
        self.assertTrue(ok, mismatches)
        self.assertEqual(set(artifacts), {
            "registry/capabilities.jsonl",
            "registry/capabilities.receipt.json",
        })

    def test_public_status_is_unknown_until_provider_declares_one(self) -> None:
        artifacts = generator.build_artifacts(ROOT)
        record = json.loads(artifacts["registry/capabilities.jsonl"])
        self.assertIsNone(record["status"])
        self.assertEqual(record["id"], "axm.causal-loop.train-platform.process/v1")
        self.assertEqual(record["providers"], ["mike-axiom-mir/axm-casual-loop"])
        self.assertFalse(record["authority"]["execution"])
        self.assertFalse(record["authority"]["automaticSelection"])
        self.assertFalse(record["authority"]["canon"])

    def test_static_descriptor_drift_is_rejected_against_live_describe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            copy_fixture(fixture)
            path = fixture / "capabilities" / "causal-loop-process-v1.json"
            descriptor = json.loads(path.read_text(encoding="utf-8"))
            descriptor["engine"]["maxWavesLimit"] = 255
            path.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(generator.DiscoveryError):
                generator.build_artifacts(fixture)

    def test_authority_widening_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            copy_fixture(fixture)
            path = fixture / "capabilities" / "causal-loop-process-v1.json"
            descriptor = json.loads(path.read_text(encoding="utf-8"))
            descriptor["authority"]["merges"] = True
            path.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(generator.DiscoveryError, "provider authority drift"):
                generator.build_artifacts(fixture)

    def test_public_opt_in_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            copy_fixture(fixture)
            marker_path = fixture / ".axm" / "discovery-public.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["public"] = False
            marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(generator.DiscoveryError, "public discovery marker drift"):
                generator.build_artifacts(fixture)

    def test_symlinked_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            copy_fixture(fixture)
            license_path = fixture / "LICENSE"
            license_path.unlink()
            try:
                license_path.symlink_to(ROOT / "LICENSE")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            with self.assertRaisesRegex(generator.DiscoveryError, "regular non-symlink"):
                generator.build_artifacts(fixture)

    def test_generated_output_drift_is_detected_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            copy_fixture(fixture)
            generator.write_artifacts(fixture)
            registry = fixture / "registry" / "capabilities.jsonl"
            original = registry.read_text(encoding="utf-8")
            registry.write_text(original + "\n", encoding="utf-8")
            ok, mismatches, _ = generator.check_artifacts(fixture)
            self.assertFalse(ok)
            self.assertEqual(mismatches, ["registry/capabilities.jsonl"])


if __name__ == "__main__":
    unittest.main()
