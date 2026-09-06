import copy
import json
from pathlib import Path
import subprocess
import unittest

from scripts.build_derived import model_display_order


ROOT = Path(__file__).resolve().parents[1]


class ModelOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = json.loads((ROOT / "data/catalog/models.json").read_text())["models"]
        cls.policy = json.loads((ROOT / "data/presentation/model-order.json").read_text())

    def test_current_featured_and_preferred_providers_lead(self):
        before = copy.deepcopy(self.models)
        order = model_display_order(self.models, self.policy)
        rows = sorted(self.models, key=lambda model: order[model["id"]])
        self.assertEqual([row["id"] for row in rows[:len(self.policy["featured_models"])]], self.policy["featured_models"])
        preferred = set(self.policy["preferred_providers"])
        current = [row for row in rows if row["status"] in {"active", "preview", "restricted"} and not set(row["tags"]) & {"上一代", "历史"}]
        positions = [row["provider"] in preferred for row in current]
        self.assertEqual(positions, sorted(positions, reverse=True))
        self.assertEqual(self.models, before, "presentation sort mutated canonical data")
        self.assertEqual(len(set(order.values())), len(self.models))
        self.assertLess(order["openai/gpt-5.6-terra@2026-07-09"], order["openai/gpt-5.6-luna@2026-07-09"])
        self.assertEqual(order, model_display_order(list(reversed(self.models)), self.policy))

    def test_dates_history_and_missing_scores_do_not_imply_strength(self):
        rows = [
            {"id": "a", "provider": "OpenAI", "status": "active", "release_date": "2026-09-01", "tags": ["旗舰"]},
            {"id": "b", "provider": "OpenAI", "status": "active", "release_date": "2026-09-02", "tags": ["旗舰"]},
            {"id": "c", "provider": "OpenAI", "status": "previous", "release_date": "2026-09-03"},
            {"id": "d", "provider": "Other", "status": "active"},
            {"id": "e", "provider": "OpenAI", "status": "active", "release_date": None, "tags": ["旗舰"]},
        ]
        policy = {**self.policy, "featured_models": []}
        order = model_display_order(rows, policy)
        self.assertEqual(sorted(order, key=order.get), ["b", "a", "e", "d", "c"])
        rows[0]["scores"] = {"unrelated": {"value": 999999}}
        self.assertEqual(order, model_display_order(rows, policy))

    def test_invalid_policy_fails_build_instead_of_silently_ignoring(self):
        for overrides in (
            {"featured_models": ["unknown-model"]},
            {"featured_models": [self.models[0]["id"]] * 2},
            {"preferred_providers": "OpenAI"},
            {"reviewed_at": "not-a-date"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                model_display_order(self.models, {**self.policy, **overrides})

    def test_all_three_frontend_views_and_explicit_sorts(self):
        result = subprocess.run(["node", str(ROOT / "tests/model_order_harness.js")], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
