"""Exercise browser event handlers, roster identity remapping and round displays."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UIRegressionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for UI regression checks')
    def test_browser_regressions(self):
        result = subprocess.run(['node', '--test', str(ROOT / 'tests' / 'test_ui_regressions.cjs')],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
