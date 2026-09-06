import pathlib
import subprocess
import unittest


class FocusTests(unittest.TestCase):
    def test_focus_and_source_semantics(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        run = subprocess.run(
            ["node", str(root / "tests/focus_semantics_harness.js"), str(root / "app.js")],
            text=True, capture_output=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
