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


if __name__ == "__main__":
    unittest.main()
