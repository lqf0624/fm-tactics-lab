import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import desktop_storage as storage


class RunSummaryTests(unittest.TestCase):
    def test_read_lock_preserves_checkpoint_and_releases_latest_completed_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            target = folder / "summary.json"
            pending = folder / "summary.pending.json"
            storage.write_json_atomic(target, {"completed": 0})
            busy = PermissionError("sharing violation")
            busy.winerror = 5
            original = storage.os.replace

            def locked(src, dst):
                if dst == target:
                    raise busy
                return original(src, dst)

            with patch.object(storage.os, "replace", side_effect=locked):
                for completed in (1, 2):
                    storage.write_json_atomic(pending, {"completed": completed})
                    self.assertFalse(storage.publish_summary(folder))
                self.assertEqual(json.loads(target.read_text()), {"completed": 0})
                self.assertEqual(json.loads(pending.read_text()), {"completed": 2})
            self.assertTrue(storage.publish_summary(folder))
            self.assertEqual(json.loads(target.read_text()), {"completed": 2})
            self.assertEqual(list(folder.iterdir()), [target])
