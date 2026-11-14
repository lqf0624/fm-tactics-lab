"""Prepare/build the optional research edition without editing the upstream tree."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ADDON=Path(__file__).resolve().parent


def normalized_source(data, name):
    if b'\0' not in data and not name.endswith('.png'):
        return data.replace(b'\r\n',b'\n')
    return data


def digest(data, name, normalize=False):
    if normalize:
        data=normalized_source(data,name)
    return hashlib.sha256(data).hexdigest()


def safe_file(root, name):
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe manifest path: '+name)
    path=root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError('Path escapes source tree: '+name)
    return path


def validate_inputs(root, addon=ADDON):
    manifest=json.loads((addon/'manifest.json').read_text(encoding='utf8'))
    for name,expected in manifest['baseline_files'].items():
        path=safe_file(root,name)
        if not path.is_file() or digest(path.read_bytes(),name,True)!=expected:
            raise ValueError('Base source differs: '+name+'; use upstream commit '+manifest['upstream_commit'])
    for name,expected in manifest['overlay_files'].items():
        path=safe_file(addon/'overlay',name)
        if not path.is_file() or digest(path.read_bytes(),name)!=expected:
            raise ValueError('Feature file checksum mismatch: '+name)
    patch=addon/'patches/integration.patch'
    if hashlib.sha256(patch.read_bytes()).hexdigest()!=manifest['patch_sha256']:
        raise ValueError('Integration patch checksum mismatch')
    return manifest


def prepare(root, destination_parent, addon=ADDON):
    manifest=validate_inputs(root,addon)
    if not shutil.which('git'):
        raise ValueError('Git is required to apply the reviewed integration patch')
    destination_parent.mkdir(parents=True,exist_ok=True)
    workspace=Path(tempfile.mkdtemp(prefix='workspace-',dir=destination_parent))
    for name in manifest['baseline_files']:
        dest=safe_file(workspace,name);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(normalized_source(safe_file(root,name).read_bytes(),name))
    # A private Git directory keeps git apply independent of the caller's checkout.
    subprocess.run(['git','init','--quiet',str(workspace)],check=True)
    subprocess.run(['git','config','core.autocrlf','false'],cwd=workspace,check=True)
    patch=addon/'patches/integration.patch'
    subprocess.run(['git','apply','--check',str(patch)],cwd=workspace,check=True)
    subprocess.run(['git','apply',str(patch)],cwd=workspace,check=True)
    for name in manifest['overlay_files']:
        dest=safe_file(workspace,name);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise ValueError('Overlay would replace an existing upstream file: '+name)
        shutil.copy2(safe_file(addon/'overlay',name),dest)
    # Verify that copying and patching did not alter even one input file.
    validate_inputs(root,addon)
    return workspace,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-root',type=Path,default=ADDON.parents[1])
    parser.add_argument('--official-exe',type=Path,help='Verified official release: Steam v1113 or Epic test')
    parser.add_argument('--platform',choices=('steam','epic'),default='steam')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--verify',action='store_true',help='Run Python, Node report/i18n tests and source export')
    parser.add_argument('--rebuild-native',action='store_true',help='Requires an x64 MSVC developer shell')
    parser.add_argument('--output',type=Path,help='New .exe path; existing files are never overwritten')
    args=parser.parse_args()
    if not args.prepare_only and not args.official_exe:
        parser.error('--official-exe is required unless --prepare-only is used')
    if args.rebuild_native and not shutil.which('cl'):
        parser.error('--rebuild-native requires an x64 Native Tools Command Prompt')
    if args.verify and not shutil.which('node'):
        parser.error('--verify requires Node.js')
    output=args.output.resolve() if args.output else None
    if output and (output.suffix.lower()!='.exe' or output.exists()):
        parser.error('--output must name a new .exe file')
    workspace,manifest=prepare(args.upstream_root.resolve(),ADDON/'build')
    print('Isolated workspace: '+str(workspace),flush=True)
    if args.verify:
        for command in ([sys.executable,'-m','unittest','discover','-s',str(ADDON/'tests'),'-v'],
                        [sys.executable,'-m','unittest','discover','-s','tests','-v'],
                        ['node','tests/test_attribute_report.cjs'],['node','tests/test_i18n.cjs'],
                        [sys.executable,'scripts/export_source.py']):
            subprocess.run(command,cwd=workspace,check=True)
    if not args.prepare_only:
        native=[]
        if args.rebuild_native:
            subprocess.run([sys.executable,'scripts/build_native.py','--platform',args.platform,
                            '--release-exe',str(args.official_exe.resolve())],cwd=workspace,check=True)
            native=['--native-host',str(workspace/'private'/('epic-engine' if args.platform=='epic' else 'engine')/'fm27_native/FM27Simulator.exe')]
        output=output or workspace/'dist'/('FM27-Role-Attribute-Research-'+args.platform+'.exe')
        subprocess.run([sys.executable,'scripts/repackage_release.py','--platform',args.platform,
            '--release-exe',str(args.official_exe.resolve()),'--output',str(output),*native],cwd=workspace,check=True)
    receipt={'upstream_commit':manifest['upstream_commit'],'workspace':str(workspace),
             'platform':args.platform,'native_rebuilt':args.rebuild_native,
             'output':str(output) if output else None,'upstream_files_unchanged':True}
    validate_inputs(args.upstream_root.resolve())
    (workspace/'extension-build.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps(receipt,indent=2),flush=True)


if __name__=='__main__':
    main()
