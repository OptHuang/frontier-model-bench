import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModelProfileTests(unittest.TestCase):
    """The model directory must have a source-aware profile for every release."""

    @classmethod
    def setUpClass(cls):
        cls.models_payload = json.loads((ROOT / "data/catalog/models.json").read_text())
        cls.sources = json.loads((ROOT / "data/catalog/sources.json").read_text())
        cls.profiles_payload = json.loads((ROOT / "data/catalog/model_profiles.json").read_text())

    @property
    def models(self):
        return self.models_payload.get("models", self.models_payload)

    @property
    def profiles(self):
        return self.profiles_payload.get("profiles", self.profiles_payload)

    def test_every_catalog_model_has_a_profile(self):
        model_ids = {row["id"] for row in self.models}
        profile_ids = set(self.profiles)
        self.assertEqual(model_ids, profile_ids)

    def test_profiles_have_reading_groups_and_valid_sources(self):
        source_ids = {row["id"] for row in self.sources}
        required = {"positioning", "capabilities", "best_for", "endpoint_ids", "availability", "caveats", "fact_source_ids", "last_checked"}
        for model_id, profile in self.profiles.items():
            self.assertTrue(required <= profile.keys(), model_id)
            for key in ("capabilities", "best_for", "endpoint_ids", "availability", "caveats", "fact_source_ids"):
                self.assertIsInstance(profile[key], list, f"{model_id}.{key}")
            self.assertTrue(set(profile["fact_source_ids"]) <= source_ids, model_id)
            self.assertRegex(profile["last_checked"], r"^\d{4}-\d{2}-\d{2}$", model_id)

    def test_parameter_estimates_are_explicitly_noncanonical_and_source_linked(self):
        source_ids = {row["id"] for row in self.sources}
        allowed_kinds = {"ikp_effective"}
        for model_id, profile in self.profiles.items():
            estimates = profile.get("parameter_estimates", [])
            self.assertIsInstance(estimates, list, f"{model_id}.parameter_estimates")
            for index, estimate in enumerate(estimates):
                path = f"{model_id}.parameter_estimates[{index}]"
                self.assertIsInstance(estimate, dict, path)
                self.assertIn(estimate.get("kind"), allowed_kinds, path)
                self.assertIn(estimate.get("source_id"), source_ids, path)
                self.assertRegex(estimate.get("as_of", ""), r"^\d{4}-\d{2}-\d{2}$", path)
                point = estimate.get("point_b")
                interval = estimate.get("range_b")
                self.assertIsInstance(point, (int, float), path)
                self.assertGreater(point, 0, path)
                self.assertIsInstance(interval, list, path)
                self.assertEqual(len(interval), 2, path)
                self.assertLessEqual(interval[0], point, path)
                self.assertGreaterEqual(interval[1], point, path)
                self.assertTrue(estimate.get("confidence"), path)
                self.assertTrue(estimate.get("note"), path)

                # Third-party black-box estimates must remain descriptive;
                # they never silently populate the canonical parameter fields.
                model = next(row for row in self.models if row["id"] == model_id)
                if model.get("params_total") is None:
                    self.assertIsNone(model.get("params_active"), path)

    def test_parameter_lineage_is_source_linked_and_not_silently_canonical(self):
        source_ids = {row["id"] for row in self.sources}
        models = {row["id"]: row for row in self.models}
        for model_id, profile in self.profiles.items():
            evidence_items = profile.get("parameter_evidence", [])
            self.assertIsInstance(evidence_items, list, f"{model_id}.parameter_evidence")
            for index, item in enumerate(evidence_items):
                path = f"{model_id}.parameter_evidence[{index}]"
                self.assertIn(item.get("kind"), {"base_checkpoint", "base_lineage"}, path)
                self.assertIn(item.get("source_id"), source_ids, path)
                self.assertTrue(item.get("label"), path)
                self.assertTrue(item.get("confidence"), path)
                self.assertTrue(item.get("note"), path)
                self.assertTrue(item.get("total_b") or item.get("active_b"), path)
                model = models[model_id]
                if item.get("kind") == "base_lineage":
                    self.assertIsNone(model.get("params_total"), f"{path} must not populate canonical total")
                    self.assertIsNone(model.get("params_active"), f"{path} must not populate canonical active")

    def test_vendor_approximate_counts_are_explicit(self):
        for model in self.models:
            if model.get("params_approximate"):
                self.assertIsInstance(model.get("params_total"), (int, float), model["id"])
                self.assertGreater(model["params_total"], 0, model["id"])


if __name__ == "__main__":
    unittest.main()
