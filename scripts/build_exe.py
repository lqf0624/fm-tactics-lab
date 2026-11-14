"""Build a unified Tauri executable using native adapters and CPython 3.12."""
import argparse
import hashlib
from importlib.metadata import distribution
import json
import os
import shutil
from pathlib import Path
import subprocess
import zipfile

from prepare_private import ASSETS
from generate_profile import adapter_paths
from run import ROOT, check_inputs, stage_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-home', required=True, type=Path,
                        help='Full CPython 3.12 x64 distribution containing Lib and DLLs')
    parser.add_argument('--offline', action='store_true', help='Use cached Cargo dependencies')
    args = parser.parse_args()
    engines = {}
    for platform in ('steam', 'epic'):
        check_inputs(platform)
        _, engines[platform] = adapter_paths(platform)
    python = args.python_home.resolve()
    for name in ['python.exe', 'python312.dll', 'python3.dll', 'vcruntime140.dll',
                 'vcruntime140_1.dll', 'LICENSE.txt', 'Lib', 'DLLs']:
        if not (python / name).exists():
            raise SystemExit('Missing Python runtime component: ' + name)
    build, dist = ROOT / 'build', ROOT / 'dist'
    build.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    source = build / 'source'
    stage_source(source)
    library = build / 'python312.zip'
    with zipfile.ZipFile(library, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in (python / 'Lib').rglob('*.py'):
            relative = path.relative_to(python / 'Lib')
            if relative.parts[0] not in {'site-packages', 'ensurepip', 'idlelib', 'tkinter', 'turtledemo', 'test', 'lib2to3'}:
                archive.write(path, relative.as_posix())
    payload = build / 'payload.zip'
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as archive:
        # Use explicit source types and asset paths, never archive the working directory.
        for original in (ROOT / 'src').rglob('*'):
            if original.is_file() and original.suffix in {'.py', '.js', '.css', '.html'} and '__pycache__' not in original.parts:
                relative = original.relative_to(ROOT / 'src')
                archive.write(source / relative, 'source/' + relative.as_posix())
        archive.write(ROOT / 'private/catalog.json', 'source/tactics_ui/catalog.json')
        # Keep the save reader and its licenses alongside the bundled Python runtime.
        for package, module in [('fmsave', 'fmsave'), ('backports-zstd', 'backports/zstd')]:
            dependency = distribution(package)
            for entry in dependency.files:
                name = entry.as_posix()
                if '__pycache__' in entry.parts:
                    continue
                if name.startswith(module + '/') or entry.parts[0].endswith('.dist-info'):
                    archive.write(dependency.locate_file(entry), 'source/vendor/' + name)
        for name in ['python.exe', 'python312.dll', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt']:
            archive.write(python / name, 'python/' + name)
        for path in (python / 'DLLs').iterdir():
            if path.suffix.lower() in {'.pyd', '.dll'}:
                archive.write(path, 'python/DLLs/' + path.name)
        archive.write(library, 'python/python312.zip')
        for name in ASSETS:
            archive.write(ROOT / 'private/engine' / name, 'engine/' + name)
        for platform, engine in engines.items():
            target = 'engine/fm27_native' if platform == 'steam' else 'engine/fm27_native/epic'
            for name in ('FM27Simulator.exe', 'engine_compat_profile.json', 'adapter_version.json'):
                archive.write(engine / 'fm27_native' / name, f'{target}/{name}')
    target = Path(os.environ.get('CARGO_TARGET_DIR', build / 'tauri-target')).resolve()
    toolchain_target = 'x86_64-pc-windows-msvc'
    command = ['cargo', 'build', '--release', '--locked', '--target', toolchain_target, '--target-dir', str(target)]
    if args.offline:
        command.append('--offline')
    subprocess.run(command, cwd=ROOT / 'tauri', check=True)
    version = 'v1114'
    exe = dist / f'FM27-Tactics-Lab-{version}.exe'
    shutil.copyfile(target / toolchain_target / 'release/fm27-tactics-lab.exe', exe)
    adapters = {platform: hashlib.sha256((engine / 'fm27_native/FM27Simulator.exe').read_bytes()).hexdigest()
                for platform, engine in engines.items()}
    manifest = {'version': version, 'file': exe.name, 'bytes': exe.stat().st_size, 'transport': 'stdio',
                'payload_sha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
                'native_adapters': adapters, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    (dist / 'private-build.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
