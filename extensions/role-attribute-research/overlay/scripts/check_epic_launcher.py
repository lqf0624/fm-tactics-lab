"""Test the actual Epic launcher with a synthetic service and descendant tree.

No game is loaded; this proves process ownership, not native match behavior.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

from acceptance_epic import process_rows
from repackage_release import ROOT, verified_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official-epic-exe', type=Path, required=True)
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='fm27-epic-launcher-'))
    raw = verified_payload(args.official_epic_exe.read_bytes(), 'epic')
    payload = folder / 'fixture.zip'
    with ZipFile(BytesIO(raw)) as original, ZipFile(payload, 'w', ZIP_DEFLATED) as output:
        for item in original.infolist():
            if item.filename.startswith('python/'):
                output.writestr(item.filename, original.read(item))
        output.write(ROOT / 'tests/launcher_lifecycle_fixture.py', 'source/desktop_server.py')
        output.writestr('engine/fm27_native/FM27Simulator.exe', b'fixture marker; not executed')
        output.writestr('engine/fm27_native/editor_manual_default.json', '{}')
    exe = folder / 'Epic-Launcher-Fixture.exe'
    subprocess.run(['C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe', '/nologo',
        '/target:winexe', '/platform:x64', '/define:EPIC_BUILD', '/utf8output',
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
        '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
        '/resource:' + str(payload) + ',DesktopPayload', '/out:' + str(exe), str(ROOT / 'Launcher.cs')], check=True)
    report = {'kind': 'synthetic_process_tree', 'epic_native_match_verified': False, 'checks': []}
    try:
        for force in (False, True):
            data = folder / ('forced' if force else 'graceful')
            child = subprocess.Popen([str(exe), '--test-lifecycle', '--no-browser', '--data-dir',
                str(data), '--game-root', str(folder)], creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 30
                while not all((data / name).is_file() for name in ('leaf.pid', 'child.pid', 'server.pid', 'url.txt')):
                    if time.monotonic() > deadline or child.poll() is not None:
                        raise RuntimeError('Fixture failed to start: ' + str(data))
                    time.sleep(.2)
                pids = {int((data / name).read_text()) for name in ('leaf.pid', 'child.pid', 'server.pid')}
                pids.add(child.pid)
                before = {r['ProcessId']: r['CreationDate'] for r in process_rows() if r['ProcessId'] in pids}
                assert len(before) == 4, 'Expected launcher, service, worker and grandchild'
                if force:
                    child.kill()
                else:
                    base = (data / 'url.txt').read_text(encoding='utf-8-sig')
                    req = urllib.request.Request(base + '/api/desktop-shutdown', data=b'{}',
                        headers={'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        assert json.load(response)['accepted']
                child.wait(timeout=35)
                deadline = time.monotonic() + 10
                while True:
                    remaining = [r['ProcessId'] for r in process_rows() if r['ProcessId'] in before
                                 and before[r['ProcessId']] == r['CreationDate']]
                    if not remaining:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError('Descendants remain: ' + str(remaining))
                    time.sleep(.2)
                report['checks'].append({'mode': 'forced' if force else 'graceful', 'passed': True,
                                         'tracked_processes': len(before)})
                print('PASS', report['checks'][-1], flush=True)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        print('Evidence: ' + str(folder / 'report.json'), flush=True)


if __name__ == '__main__':
    main()
