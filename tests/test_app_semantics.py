from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AppSemanticsTests(unittest.TestCase):
    def test_system_runs_are_filtered_lazy_paginated_and_searchable(self) -> None:
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "app_semantics_harness.js"), str(ROOT / "app.js")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
