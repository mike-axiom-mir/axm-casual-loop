from __future__ import annotations

from copy import deepcopy
import unittest

from causal_loop.atlas_verifier import verify_atlas
from causal_loop.engine import deterministic_hash
from causal_loop.explorer import bounded_schedule_cases, explore_schedule_space
from causal_loop.train_platform import build_engine, initial_state


def build_small_atlas() -> tuple[dict, object]:
    engine = build_engine()
    cases = bounded_schedule_cases(
        ("BLOCK_DOOR",),
        (0,),
        max_actions_per_case=1,
        include_empty=False,
    )
    atlas = explore_schedule_space(engine, initial_state(), cases)
    return atlas, engine


def reseal(atlas: dict) -> None:
    unsigned = deepcopy(atlas)
    unsigned.pop("atlasHash", None)
    atlas["atlasHash"] = deterministic_hash(unsigned)


class AtlasVerifierTests(unittest.TestCase):
    def test_accepts_real_generated_atlas_and_binds_expected_engine(self) -> None:
        atlas, engine = build_small_atlas()

        first = verify_atlas(
            atlas,
            expected_engine_signature=engine.engine_signature,
            expected_loop_id=engine.spec.loop_id,
            expected_loop_version=engine.spec.version,
        )
        second = verify_atlas(
            atlas,
            expected_engine_signature=engine.engine_signature,
            expected_loop_id=engine.spec.loop_id,
            expected_loop_version=engine.spec.version,
        )

        self.assertTrue(first["accepted"])
        self.assertEqual(first["atlasHash"], atlas["atlasHash"])
        self.assertEqual(first["caseCount"], 1)
        self.assertEqual(first["verificationHash"], second["verificationHash"])

    def test_rejects_body_tamper_without_reseal(self) -> None:
        atlas, _ = build_small_atlas()
        atlas["summary"]["caseCount"] += 1

        with self.assertRaisesRegex(ValueError, "atlasHash"):
            verify_atlas(atlas)

    def test_rejects_self_consistent_forged_summary(self) -> None:
        atlas, _ = build_small_atlas()
        atlas["summary"]["caseCount"] += 1
        reseal(atlas)

        with self.assertRaisesRegex(ValueError, "summary"):
            verify_atlas(atlas)

    def test_rejects_self_consistent_forged_path_group(self) -> None:
        atlas, _ = build_small_atlas()
        only_hash = next(iter(atlas["pathGroups"]))
        atlas["pathGroups"][only_hash] = []
        reseal(atlas)

        with self.assertRaisesRegex(ValueError, "pathGroups"):
            verify_atlas(atlas)

    def test_rejects_duplicate_case_identity_even_when_resealed(self) -> None:
        atlas, _ = build_small_atlas()
        atlas["cases"].append(deepcopy(atlas["cases"][0]))
        reseal(atlas)

        with self.assertRaisesRegex(ValueError, "duplicate caseId"):
            verify_atlas(atlas)

    def test_rejects_engine_identity_mismatch(self) -> None:
        atlas, _ = build_small_atlas()

        with self.assertRaisesRegex(ValueError, "expected engine"):
            verify_atlas(atlas, expected_engine_signature="0" * 64)


if __name__ == "__main__":
    unittest.main()
