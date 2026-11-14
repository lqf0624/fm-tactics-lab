from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from acceptance_epic import descendants


class AcceptanceProcessTests(unittest.TestCase):
    def test_cleanup_scope_tracks_only_test_launcher_tree(self):
        rows = [dict(ProcessId=pid, ParentProcessId=parent, CreationDate=str(pid))
                for pid, parent in [(20,10),(40,30),(10,1),(30,20),(99,1)]]
        self.assertEqual(descendants(rows, 10), {10:'10',20:'20',30:'30',40:'40'})
        self.assertEqual(descendants(rows, 999), {})
