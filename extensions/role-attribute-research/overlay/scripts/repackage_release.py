"""Package current Python/UI and launcher with a verified Steam or Epic runtime.

By default this reuses the official native binary. When changing native code,
build it with build_native.py and pass the result via --native-host.
"""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
import struct
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

from prepare_private import TRUSTED_RELEASES

ROOT = Path(__file__).resolve().parents[1]
V1113 = 'fc4e7c7d0f9a61b038700c43ad9707af3971416706f8e46837e8a26cfdca7acb'
EPIC = '31c38715e82d3e7ad15dbdcc3f68bb0e4d0fe676c319e9a245b25915d89fcbc8'
EPIC_PAYLOAD = '5632549640ef52e56bf11320fc570f9205c4393291c76c2ac5681f182fd3634b'
EPIC_DLL = 'ebf6fcf57f554dc7178fb2afa4e1fd4d6e6dcb693f65a1a11216abb8d00c8396'


def verified_payload(raw, platform):
    expected = EPIC if platform == 'epic' else V1113
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Expected the verified official ' + platform + ' executable')
    start, end = raw.find(b'PK\x03\x04'), raw.rfind(b'PK\x05\x06')
    finish = end + 22 + struct.unpack_from('<H', raw, end + 20)[0]
    data = raw[start:finish]
    digest = EPIC_PAYLOAD if platform == 'epic' else TRUSTED_RELEASES[V1113]
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Official payload checksum mismatch')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', choices=('steam', 'epic'), default='steam')
    parser.add_argument('--native-host', type=Path, help='Locally rebuilt native host for this platform')
    parser.add_argument('--csc', type=Path, default=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'))
    args = parser.parse_args()
    if args.output.resolve() == args.release_exe.resolve():
        parser.error('Output must not overwrite the official input')
    raw = args.release_exe.read_bytes()
    original_bytes = verified_payload(raw, args.platform)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = ROOT / ('build/repackage-' + args.platform) / 'payload.zip'
    payload.parent.mkdir(parents=True, exist_ok=True)
    overrides = {'source/' + p.relative_to(ROOT / 'src').as_posix(): p
                 for p in (ROOT / 'src').rglob('*')
                 if p.is_file() and p.suffix in {'.py', '.js', '.html', '.css', '.json'}
                 and '__pycache__' not in p.parts}
    with ZipFile(BytesIO(original_bytes)) as original, ZipFile(payload, 'w', ZIP_DEFLATED) as archive:
        native_bytes = args.native_host.read_bytes() if args.native_host else original.read('engine/fm27_native/FM27Simulator.exe')
        native_sha = hashlib.sha256(native_bytes).hexdigest()
        profile = json.loads(original.read('engine/fm27_native/engine_compat_profile.json'))
        if args.platform == 'epic' and profile['reference_sha256'] != EPIC_DLL:
            raise ValueError('Epic adapter reference DLL mismatch')
        written = set()
        for item in original.infolist():
            path = overrides.get(item.filename)
            content = path.read_bytes() if path else original.read(item)
            if item.filename == 'engine/fm27_native/FM27Simulator.exe':content = native_bytes
            if args.native_host and item.filename == 'engine/fm27_native/adapter_version.json':
                content = (ROOT / 'native' / ('epic_adapter_version.json' if args.platform=='epic' else 'adapter_version.json')).read_bytes()
            archive.writestr(item.filename, content)
            written.add(item.filename)
        for name, path in overrides.items():
            if name not in written:
                archive.write(path, name)
    subprocess.run([str(args.csc), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/utf8output',
        *(['/define:EPIC_BUILD'] if args.platform == 'epic' else []),
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
        '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
        '/resource:' + str(payload) + ',DesktopPayload', '/out:' + str(output), str(ROOT / 'Launcher.cs')], check=True)
    print(str(output))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = dict(platform=args.platform, sha256=digest, native_sha256=native_sha,
        official_sha256=hashlib.sha256(raw).hexdigest(), reference_dll_sha256=profile['reference_sha256'],
        native_host_override=bool(args.native_host), native_match_verified=False)
    output.with_suffix('.build.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print('SHA256=' + digest)


if __name__ == '__main__':
    main()
