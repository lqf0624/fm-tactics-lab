from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from repackage_release import verified_payload


class RepackageTests(unittest.TestCase):
    def test_untrusted_input_is_rejected_before_archive_parsing(self):
        for platform in ('steam', 'epic'):
            with self.subTest(platform=platform), self.assertRaisesRegex(ValueError, platform):
                verified_payload(b'not an official release', platform)
