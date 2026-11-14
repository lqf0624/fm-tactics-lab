# Building FM Tactics Lab v1114

This source includes the career-save reader and same-league match mode shipped in v1108.5.

## Requirements

- Windows x64, full CPython 3.12 x64, MSVC C++17, the Windows SDK, Rust MSVC toolchain and WebView2.
- A local FM27 installation; the adapter reference build is `27.0.0+2493426`.
- A verified v1108.5 EXE from this repository's Releases, used to supply the matching initial inputs.

Install the save reader and its compression dependency from requirements.txt in the build environment.

## Prepare local inputs

Run these commands from the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/prepare_private.py --release-exe "D:\Downloads\FM27-Tactics-Lab-v1108.5.exe"
```

The script checks the original EXE and embedded payload SHA256, then reads only the named input assets into ignored `private/` directories. It does not execute the EXE. An existing matching asset directory can alternatively be supplied with `--assets-root` and `--catalog`.

## Build the native adapter

In an **x64 Native Tools Command Prompt for Visual Studio**:

```bat
.venv\Scripts\python.exe scripts\build_native.py --reference-dll "D:\Games\Football Manager 27\fm_Data\Plugins\x86_64\game_plugin.dll"
```

The public repository contains range metadata and digests. The script reconstructs comparison bytes from the exact reference DLL on your machine, verifies every range, then compiles the checked-in C++ host. Generated function bytes remain in ignored local outputs.

## Run from source

```powershell
.venv\Scripts\python.exe scripts/run.py --game-root "D:\Games\Football Manager 27"
```

Open the printed loopback URL after startup. Press `Ctrl+C` to stop the source edition.

## Build a local desktop EXE

```powershell
.venv\Scripts\python.exe scripts/build_exe.py --python-home "D:\Python312"
```

Supply a full CPython 3.12 x64 distribution containing `Lib`, `DLLs`, `python312.dll`, the runtime libraries and `LICENSE.txt`. Prepare both native adapters with matching Steam and Epic game DLLs, using `--platform epic` for the Epic native build. The Tauri build outputs one `dist/FM27-Tactics-Lab-v1114.exe` with both adapters.

The build script packages the save reader from the active Python environment. The release EXE and a local build can have different hashes.

## Validate and export source

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/export_source.py
```

The exporter uses an explicit source allowlist, checks for workstation paths and common credential formats, and writes file digests inside the archive. It excludes game DLLs, runtime data, input snapshots and generated comparison bytes.

The EXE release is a separate asset authorized for distribution by the maintainer. Its embedded initial inputs and comparison data are outside the MIT grant for tool code. See [third-party notices](../THIRD_PARTY_NOTICES.md).
