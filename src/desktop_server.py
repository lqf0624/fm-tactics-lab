"""Isolated desktop service, using the existing native engine installation."""
import json
import os
from pathlib import Path
import re
import sys
import winreg


GAME_PLUGIN = 'fm_Data/Plugins/x86_64/game_plugin.dll'


def epic_installations(manifests):
    for item in sorted(manifests.glob('*.item')):
        try:
            entry = json.loads(item.read_text(encoding='utf-8-sig'))
            if entry.get('DisplayName', '').casefold() != 'football manager 27':
                continue
            if entry.get('bIsIncompleteInstall') or not entry.get('InstallLocation'):
                continue
            location = Path(entry['InstallLocation'])
            if location.is_absolute():
                yield location
        except (OSError, ValueError, TypeError, AttributeError):
            continue


def discover_game(native):
    from desktop_engine import reference_matches, sha

    relative = Path('steamapps/common/Football Manager 27')
    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        candidates.append(steam/relative)
        libraries = (steam/'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
        for library in re.findall(r'"path"\s+"([^"]+)"', libraries):
            candidates.append(Path(library.replace('\\\\', '\\'))/relative)
    except (OSError, UnicodeError):
        pass
    program_data = Path(os.environ.get('ProgramData', r'C:\ProgramData'))
    epic = list(epic_installations(program_data/'Epic/EpicGamesLauncher/Data/Manifests'))
    candidates.extend(Path(f'{letter}:/SteamLibrary')/relative for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ')
    first = ''
    for path in dict.fromkeys([*candidates, *epic]):
        plugin = path/GAME_PLUGIN
        if not plugin.is_file():
            continue
        first = first or str(path)
        try:
            fingerprint = sha(plugin)
            if reference_matches(native, fingerprint) or reference_matches(native/'epic', fingerprint):
                return str(path)
        except (OSError, ValueError, KeyError):
            continue
    return first


root = Path(os.environ['FM27_ENGINE_ROOT']).resolve()
if '--stdio' in sys.argv and not os.environ.get('FM27_GAME_ROOT'):
    config = Path(os.environ['FM27_DESKTOP_DATA'])/'game-root.txt'
    try:
        saved_game = config.read_text(encoding='utf-8-sig').strip()
    except FileNotFoundError:
        saved_game = ''
    os.environ['FM27_GAME_ROOT'] = (
        saved_game if saved_game and (Path(saved_game)/GAME_PLUGIN).is_file()
        else discover_game(root/'fm27_native') or saved_game
    )

required=['fm27_native/FM27Simulator.exe','fm27_native/editor_manual_default.json','fm27_native/editor_advanced_snapshot.json','fm27_native/editor_setpieces_default.json','fm27_research/setpiece_enum_catalog.json']
missing=[name for name in required if not(root/name).is_file()]
if missing:raise SystemExit('Engine workspace is incomplete: '+', '.join(missing))
from fm27_tactics_server import main
main()
