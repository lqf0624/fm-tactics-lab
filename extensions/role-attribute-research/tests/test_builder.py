import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('addon_build',Path(__file__).resolve().parents[1]/'build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


class IsolatedBuilderTests(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory)/'upstream';addon=Path(directory)/'addon'
        root.mkdir();(addon/'overlay').mkdir(parents=True);(addon/'patches').mkdir()
        (root/'source.txt').write_bytes(b'old\n');(addon/'overlay/new.txt').write_bytes(b'new\n')
        patch=b'diff --git a/source.txt b/source.txt\n--- a/source.txt\n+++ b/source.txt\n@@ -1 +1 @@\n-old\n+changed\n'
        (addon/'patches/integration.patch').write_bytes(patch)
        manifest={'upstream_commit':'test','baseline_files':{'source.txt':build.digest(b'old\n','source.txt',True)},
                  'overlay_files':{'new.txt':build.digest(b'new\n','new.txt')},'patch_sha256':hashlib.sha256(patch).hexdigest()}
        (addon/'manifest.json').write_text(json.dumps(manifest))
        return root,addon

    def test_patch_and_overlay_only_touch_new_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            root,addon=self.fixture(d)
            workspace,_=build.prepare(root,Path(d)/'output',addon)
            self.assertEqual((root/'source.txt').read_bytes(),b'old\n')
            self.assertFalse((root/'new.txt').exists())
            self.assertEqual((workspace/'source.txt').read_bytes(),b'changed\n')
            self.assertEqual((workspace/'new.txt').read_bytes(),b'new\n')

    def test_changed_base_or_overlay_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root,addon=self.fixture(d)
            (root/'source.txt').write_bytes(b'user edit\n')
            with self.assertRaisesRegex(ValueError,'Base source differs'):build.validate_inputs(root,addon)
            (root/'source.txt').write_bytes(b'old\n')
            (addon/'overlay/new.txt').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'Feature file checksum'):build.validate_inputs(root,addon)

    def test_platform_newlines_do_not_change_baseline(self):
        self.assertEqual(build.digest(b'line\r\n','file.py',True),build.digest(b'line\n','file.py',True))
        with tempfile.TemporaryDirectory() as d:
            root,addon=self.fixture(d)
            (root/'source.txt').write_bytes(b'old\r\n')
            workspace,_=build.prepare(root,Path(d)/'output',addon)
            self.assertEqual((workspace/'source.txt').read_bytes(),b'changed\n')
            self.assertEqual((root/'source.txt').read_bytes(),b'old\r\n')

    def test_paths_cannot_escape_workspace(self):
        for name in ['../outside','/absolute','C:/outside','folder\\escape']:
            with self.subTest(name=name), self.assertRaises(ValueError):build.safe_file(Path.cwd(),name)
