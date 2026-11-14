"""Read display identities from FM's local Chinese database and saved match sheets."""
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading

# Private zstd is used by the HTTP process as well as the isolated save reader.
vendor = str(Path(__file__).with_name('vendor'))
if vendor not in sys.path:
    sys.path.insert(0,vendor)

from desktop_game_db_names import _decompress_frames, _lang_db_path

LOCK = threading.RLock()
VERSION = 7
ROW = re.compile(rb'\x02(.{4})([\x01-\x63])([\x00\x01])\x02(.{4})\x02(.{4})\xff', re.S)
CLUB = rb'\x03\x02(.{4})\x02(.{4})\x00\x00\x01.{4}\2\x00'
PAIR = re.compile(CLUB + CLUB.replace(rb'\2', rb'\4'), re.S)
LEX = re.compile(rb'\xff{4}.{3}([\x03-\xf0]\x00{3})[\xe3-\xe9][\x80-\xbf]{2}', re.S)
CJK = re.compile(r'[\u3400-\u9fff]')


def u32(b):
    return int.from_bytes(b, 'little')


def fm_text(b, i):
    if i + 4 > len(b):
        raise ValueError('truncated string')
    length = u32(b[i:i+4])
    end = i + 4 + length
    if length > 512 or end > len(b):
        raise ValueError('invalid string length')
    return b[i+4:end].decode('utf8'), end


def versus(raw):
    b = _decompress_frames(raw, 8 * 1024**2)
    if not b.startswith(b'\x03\x01moa.') or b[12:36] != b'VERSUS_TEAM_TYPE_HANDLER':
        raise ValueError('请选择游戏导出的对战球队 FMF')
    def field(block, tag):
        i = block.find(tag + b'\x01\x1a')
        return fm_text(block, i+6)[0] if i >= 0 else ''
    club = field(b, b'nsCT')
    rows = []
    for block in b.split(b'unsP\x01\x11')[1:]:
        if len(block) < 8 or block[1:6] != b'qspP\x01':
            continue
        first, last, common, zh = [field(block, tag) for tag in (b'anfP', b'ansP', b'ancP', b'nlfP')]
        rows.append({'name': common or (first+' '+last).strip(), 'zh': zh if CJK.search(zh) else '',
                     'number': block[0] if 1 <= block[0] <= 99 else None})
    if not club or len(rows) < 11:
        raise ValueError('球队导出文件未包含完整名单')
    return club, rows



# Layout confirmed against the Chinese team export for FM27 builds 2486695 and
# 2503222. Other builds keep the historical match-sheet fallback.
REGISTRATION_BUILDS = {'27.0.0+2486695', '27.0.1+2503222'}
# The FM27 dictionary interchanges the Chinese components for this identity.
# The UID and Latin name guard against homonyms and generated players.
NAME_CORRECTIONS = {(2000239358, 'Kuryu Matsuki'): '松木玖生'}


def registered_shirts(save, people):
    """Only use in-force records for the player's current fielding club."""
    from fmsave._layouts import ContractLayout, find_layout
    from fmsave.readers.contracts import build_contract_decoder
    from fmsave.readers.player_scan import window_end

    info = save.info
    if info.build not in REGISTRATION_BUILDS or info.section_schemas.get('game_db') != 4000:
        return {}
    context = save._context
    layout = find_layout(ContractLayout,'game_db',4000,info.build).layout
    decoder = build_contract_decoder(layout,context.club_index(),info.game_date,info.file_name)
    if decoder.team_id_offset != 9 or decoder.selector_offset != 5:
        return {}
    records = context.player_records()
    selected = {p.uid:p for p in people}
    result = {}
    with context.section('game_db') as db:
        for i, uid in enumerate(records.uids):
            player = selected.get(uid)
            if player is None:
                continue
            start = records.record_offsets[i]
            end = window_end(records,i,len(db))
            chain = decoder._find_chain_records(db,start,end,i+1==len(records.uids),records.pindexes[i])
            if not chain:
                continue
            numbers = set()
            for at, record in zip(*chain):
                club, _, _, _, began, expires, terms = record[:7]
                if club != player.club_uid or not began or began>info.game_date or at-12<start:
                    continue
                if terms:
                    if not expires or expires<info.game_date:
                        continue
                elif not (player.on_loan and record[2]==player.team_id and began==player.loan_start
                          and player.loan_end and info.game_date<=player.loan_end):
                    continue
                # u16 twelve bytes before the validated contract tag. A low byte
                # of 0xff denotes an unassigned shirt in the verified builds.
                value = int.from_bytes(db[at-12:at-10], 'little')
                if value in (0,255) or 1 <= value <= 99:
                    numbers.add(value)
            assigned = numbers - {0,255}
            if len(assigned)==1:
                result[player.unique_id] = assigned.pop()
            elif numbers and not assigned:
                result[player.unique_id] = None
    return result


def summary_names(save, people, shirts, managed):
    """Join the localized squad in the save summary to unique registered shirts."""
    if save.info.section_schemas.get('save_game_summary') != 31:
        return {}
    owners = defaultdict(list)
    for p in people:
        if p.team_slot==0 and shirts.get(p.unique_id):
            owners[p.club_uid,shirts[p.unique_id]].append(p.unique_id)
    names = {}
    with save._context.section('save_game_summary') as data:
        for club in managed:
            marker = club.to_bytes(4,'little')
            pos = data.find(marker)
            while pos >= 0:
                # In revision 31 the repeating club reference precedes the
                # counted list by 234 bytes, the manager club by 542 bytes.
                start = pos+234
                pos = data.find(marker,pos+1)
                if start<542 or data[start-542:start-538]!=marker:
                    continue
                count = u32(data[start:start+4])
                if not 11 <= count <= 100:
                    continue
                at = start+4
                try:
                    labels = []
                    for _ in range(count):
                        value, at = fm_text(data,at)
                        labels.append(value)
                except (UnicodeError,ValueError):
                    continue
                if u32(data[at:at+4])!=count or at+4+count>len(data):
                    continue
                nums = data[at+4:at+4+count]
                for value,num in zip(labels,nums):
                    ids = owners.get((club,num),())
                    if len(ids)==1 and nums.count(num)==1 and CJK.search(value) and value.isprintable():
                        names[ids[0]] = value
    return names


def game_names(path, people, nation_ids):
    if not path:
        return {}
    wanted = {x.casefold() for p in people for x in (p.first_name, p.last_name, p.name, p.common_name) if x}
    db = _decompress_frames(path.read_bytes(), 450 * 1024**2)
    labels = defaultdict(lambda: defaultdict(set))
    for m in LEX.finditer(db):
        i = m.start()+7
        try:
            zh, i = fm_text(db, i)
            first, i = fm_text(db, i)
            last, i = fm_text(db, i)
            common, i = fm_text(db, i)
        except (UnicodeError, ValueError):
            continue
        if db[i:i+4] != b'\xff'*4 or db[i+5:i+7] != bytes(2):
            continue
        parts = (first.casefold(), last.casefold(), common.casefold())
        if any(v and v not in wanted for v in parts) or not any(parts):
            continue
        labels[parts][db[i+4]].add(zh)
    def lookup(parts, player):
        by_nation = labels.get(tuple((x or '').casefold() for x in parts), {})
        choices = by_nation.get(player.nation_id)
        if not choices:
            choices = {v for n in player.second_nation_ids for v in by_nation.get(n, ())}
        if not choices:
            choices = {v for vs in by_nation.values() for v in vs}
        return next(iter(choices)) if len(choices) == 1 else ''
    result = {}
    for p in people:
        nation = p.nation_id
        name = lookup((p.first_name, p.last_name, p.common_name), p)
        if p.common_name and not name:
            name = lookup(('', '', p.common_name), p) or lookup((p.common_name, '', ''), p)
        if not name and (not p.common_name or p.common_name == p.full_name):
            first = lookup((p.first_name, '', ''), p)
            last = lookup(('', p.last_name, ''), p)
            if first and last:
                name = last+first if nation_ids.get(str(nation)) in (110,111,116,124,129,135,138) else first+'·'+last
        if name:
            result[p.unique_id] = name
    return result


def match_numbers(save, data, people):
    from fmsave._container import match_file_entries, read_directory_entry
    records = save._context.player_records()
    selectors = dict(zip(records.uids, (i+1 for i in records.pindexes)))
    players = {selectors[p.uid]: p for p in people}
    fixtures = defaultdict(list)
    for f in data['fixtures']:
        if f['played'] and f['home_team_slot'] == f['away_team_slot'] == 0 and f['season_start_year'] is not None:
            fixtures[(f['home_team_id'], f['away_team_id'], f['season_start_year'], f['round_index'], f['competition_id'])].append(f)
    current_seasons = defaultdict(list)
    for f in data['fixtures']:
        if f.get('played') and f.get('date') and f.get('season_start_year') and f['home_team_slot']==f['away_team_slot']==0:
            for c in (f['home_club_uid'],f['away_club_uid']):
                current_seasons[c].append(f['season_start_year'])
    latest_season = {c:max(years) for c,years in current_seasons.items()}
    candidates = defaultdict(lambda: defaultdict(set))
    def sheet(block, fixture, teams):
        for side, club in enumerate(teams):
            rows = [m for m in ROW.finditer(block) if m[3][0] == side]
            ids = [u32(m[1]) for m in rows]
            numbers = [m[2][0] for m in rows]
            if not 11 <= len(rows) <= 32 or len(set(ids)) != len(ids) or len(set(numbers)) != len(numbers):
                continue
            for sel, num in zip(ids, numbers):
                p = players.get(sel)
                if p and p.club_uid == club and fixture['season_start_year']==latest_season.get(club):
                    candidates[p.unique_id][fixture['date']].add(num)
    marker = b'\x3c\x1f\x02'
    def extract(block, match_date=None, home_team=None):
        pair = PAIR.search(block, 0, 2048)
        if not pair or len(block) < 40:
            return
        h, hc, a, ac = map(u32, pair.groups())
        if home_team is not None and home_team != h:
            return
        key = (h, a, u32(block[16:18]), u32(block[21:23]), u32(block[35:39]))
        matches = [f for f in fixtures.get(key, ()) if (match_date is None or f['date']==match_date)
                   and (f['home_club_uid'],f['away_club_uid'])==(hc,ac)]
        if len(matches)==1:
            sheet(block, matches[0], (hc, ac))
    for entry in match_file_entries(save._container_index):
        m = re.fullmatch(r'(\d+)_(\d+)', entry.name)
        if not m or entry.extension not in ('.scm','.mst'):
            continue
        packed = int(m[2])
        year, day = packed>>17, (packed>>8)&511
        if not 1900 <= year <= 2200 or not 1 <= day <= 366:
            continue
        b = read_directory_entry(save._container_index, entry)
        if b.startswith(b'\x03\x01mst.\x00\x00'+marker):
            extract(b[8:], (date(year,1,1)+timedelta(days=day-1)).isoformat(), int(m[1]))
    with save._context.section('news') as news:
        starts = [m.start() for m in re.finditer(rb'\x3c\x1f\x02.\xff\x00\xff\x00', news, re.S)]
        for i, start in enumerate(starts):
            end = starts[i+1] if i+1<len(starts) else len(news)
            extract(news[start:min(end,start+48000)])
    result = {}
    for uid, dates in candidates.items():
        last = max(dates)
        if len(dates[last]) == 1:
            result[uid] = {'number': next(iter(dates[last])), 'date': last}
    # A later appearance with the same club shirt supersedes an older holder.
    owners = defaultdict(list)
    for p in people:
        if p.unique_id in result:
            obs = result[p.unique_id]
            owners[(p.club_uid,obs['number'])].append((obs['date'],p.unique_id))
    for entries in owners.values():
        if len(entries)>1:
            last = max(day for day,uid in entries)
            tied = sum(day==last for day,uid in entries)>1
            for day,uid in entries:
                if day<last or tied:
                    result.pop(uid,None)
    return result


def generate(folder, source, data, lang, club=None):
    import desktop_save_compat
    desktop_save_compat.install()
    import fmsave
    from desktop_save_players import selected_players
    with source.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != data['source_sha256']:
            raise ValueError('存档已更新，请重新读取存档')
    clubs = {c['uid']: c for c in data['clubs']}
    if club is not None:
        clubs = {club:data['league_clubs'][str(club)]}
    with fmsave.open(source) as save:
        people = [p for p in selected_players(save,set(clubs),True)[0] if p.unique_id is not None]
        registered = registered_shirts(save,people)
        saved_names = summary_names(save,people,registered,{c['club_uid'] for c in data['managed']})
        numbers = match_numbers(save,data,people)
        for uid,num in registered.items():
            numbers[uid] = {'number':num,'number_source':'registration','as_of':data['date']}
        holders = {(p.club_uid,registered[p.unique_id]) for p in people if registered.get(p.unique_id)}
        for p in people:
            uid = p.unique_id
            if uid not in registered and uid in numbers and (p.club_uid,numbers[uid]['number']) in holders:
                del numbers[uid]

    names = game_names(lang,people,data.get('nations',{}))
    # Older versus exports provide exact display names only. Shirts are save-specific.
    aliases = defaultdict(set)
    for f in (source.parent.parent/'exported teams').glob('*.fmf'):
        try:
            if f.stat().st_size > 2*1024**2:
                continue
            club, rows = versus(f.read_bytes())
            for row in rows:
                if row['zh']:
                    aliases[(club,row['name'].casefold())].add(row['zh'])
        except (ValueError, OSError):
            continue
    result = {}
    for p in people:
        club = clubs[p.club_uid]
        row = {'raw':p.name,'club':p.club_uid,**numbers.get(p.unique_id,{})}
        options = aliases.get((club.get('short_name'),p.name.casefold()),set())
        if p.unique_id in saved_names:
            row['zh'] = saved_names[p.unique_id]
        elif len(options)==1:
            row['zh'] = next(iter(options))
        elif (p.unique_id,p.name) in NAME_CORRECTIONS:
            row['zh'] = NAME_CORRECTIONS[p.unique_id,p.name]
        elif p.unique_id in names:
            row['zh'] = names[p.unique_id]
        result[str(p.unique_id)] = row
    return result


def read_labels(lib, key, *, force=False, club=None):
    folder = lib.folder(key)
    data = lib.index_data(folder)
    if club is not None:
        if type(club) is not int:
            raise ValueError('请选择当前存档球队')
        if any(c['uid']==club for c in data['clubs']):
            club = None
        elif str(club) not in data.get('league_clubs',{}):
            raise ValueError('请选择当前存档球队')
    path = folder/('player_display.json' if club is None else f'player_display_{club}.json')
    with LOCK:
        lang = _lang_db_path(os.environ.get('FM27_GAME_ROOT'))
        stamp = [VERSION, data['source_sha256'], str(lang), lang.stat().st_mtime_ns if lang else 0]
        if path.exists() and not force:
            try:
                cached = json.loads(path.read_text('utf8'))
            except (UnicodeError,ValueError):
                cached = None
            if isinstance(cached,dict) and cached.get('stamp') == stamp:
                return cached['rows']
        source = Path(lib._source(key,folder,data)['source'])
        with (folder/'player_display.log').open('w',encoding='utf8') as log:
            run = subprocess.run([os.environ.get('FM27_SAVE_PYTHON',sys.executable),str(Path(__file__).resolve()),
                                  str(folder),str(source),str(lang or ''),str(club) if club is not None else ''],stdout=log,stderr=log,timeout=180,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        if run.returncode:
            raise ValueError('暂时无法读取球员译名和号码，详情见 player_display.log')
        return json.loads(path.read_text('utf8'))['rows']



def import_rows(lib, key, club, payload):
    with LOCK:
        folder = lib.folder(key)
        data = lib.index_data(folder)
        clubs = {int(uid):c for uid,c in data.get('league_clubs',{}).items()}
        clubs.update({c['uid']:c for c in data['clubs']})
        if type(club) is not int or club not in clubs:
            raise ValueError('请选择当前存档球队')
        labels = current_rows(lib,key,club=club)
        rows = payload.get('rows')
        if payload.get('file_base64'):
            raw = base64.b64decode(payload['file_base64'],validate=True)
            if len(raw)>2*1024**2:
                raise ValueError('阵容文件过大')
            team, rows = versus(raw)
            if team not in (clubs[club]['name'],clubs[club]['short_name']):
                raise ValueError('导出球队与当前球队不一致')
        if not isinstance(rows,list) or not 1<=len(rows)<=5000:
            raise ValueError('无效的阵容表')
        known = {uid:p for uid,p in labels.items() if p['club']==club}
        aliases = defaultdict(set)
        for uid,p in known.items():
            for n in [p['raw'],p.get('zh')]:
                if n:
                    aliases[n.strip().casefold()].add(uid)
        changes = {}
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError('无效的球员记录')
            name = str(row.get('name') or '').strip()
            uid = str(row.get('uid') or '').strip()
            if uid and uid not in known:
                continue
            if not uid:
                choices = aliases.get(name.casefold(),set())
                if len(choices)!=1:
                    continue
                uid = next(iter(choices))
            n = str(row.get('number') or '').strip()
            if n and n not in ('-', '—', '–') and not re.fullmatch('[1-9][0-9]?',n):
                continue
            number = int(n) if n.isdigit() else None
            zh = row.get('zh') or (name if CJK.search(name) else known[uid].get('zh'))
            value = {'number':number,'date':None,'imported':True}
            if zh:
                value['zh'] = str(zh)[:128]
            if uid in changes and changes[uid]!=value:
                raise ValueError('同一球员出现多条不同记录')
            changes[uid] = value
        if not changes:
            raise ValueError('没有匹配到本队球员，请在游戏列表中加入唯一 ID')
        path = folder/'player_display_imports.json'
        overrides = json.loads(path.read_text('utf8')) if path.exists() else {}
        overrides.update(changes)
        lib.write(path,overrides)
        return {'matched':len(changes),'total':len(rows)}


def current_rows(lib,key, *, force=False,club=None):
    rows = read_labels(lib,key,force=force,club=club)
    with LOCK:
        path = lib.folder(key)/'player_display_imports.json'
        if path.exists():
            for uid,extra in json.loads(path.read_text('utf8')).items():
                if uid in rows:
                    row = rows[uid]
                    if extra.get('zh'):
                        row['zh'] = extra['zh']
                    if row.get('number_source')!='registration':
                        row.update(number=extra.get('number'),date=None,number_source='import',imported=True)
    return rows

def result_labels(lib, directory, variants):
    """Match event IDs against the exact side and roster used for each fixture."""
    cache = directory/'result_player_names.json'
    if cache.exists():
        return json.loads(cache.read_text('utf8'))
    provenance = directory/'provenance.json'
    if not provenance.exists():
        return {}
    meta = json.loads(provenance.read_text('utf8'))
    source = (meta.get('save_source') or {}).get('id')
    labels = {}
    result = {}
    complete = True
    for variant in variants:
        if not re.fullmatch(r'(?:A|B)(?:_\d+_[HA])?',variant):
            continue
        snapshot = directory/(variant+'.json')
        if not snapshot.exists():
            complete = False
            continue
        scenario = json.loads(snapshot.read_text('utf8'))
        sides = []
        for team in scenario['teams']:
            names = {}
            sides.append(names)
            binding = team.get('roster_source') or {}
            key = binding.get('id') or source
            if not key:
                continue
            club = binding.get('club_uid')
            if not any(p.get('source_uid') is not None for p in team['players']):
                continue
            lookup = (key,club)
            if lookup not in labels:
                try:
                    labels[lookup] = current_rows(lib,key,club=club)
                except (FileNotFoundError, ValueError, OSError):
                    labels[lookup] = {}
                    complete = False
            for player in team['players'][:team.get('roster_size')]:
                uid = player.get('source_uid')
                row = labels[lookup].get(str(uid))
                if row and row.get('zh') and player['name'] in (row['raw'],row['zh']):
                    event_id = uid if 'native_generation' in scenario else player['native_id']
                    names[str(event_id)] = [player['name'],row['zh']]
        result[variant] = sides
    if complete and result:
        from desktop_storage import write_json_atomic
        write_json_atomic(cache,result)
    return result


if __name__ == '__main__':
    folder, source = map(Path,sys.argv[1:3])
    lang = Path(sys.argv[3]) if sys.argv[3] else None
    data = json.loads((folder/'dataset.json').read_text('utf8'))
    club = int(sys.argv[4]) if len(sys.argv)>4 and sys.argv[4] else None
    rows = generate(folder,source,data,lang,club)
    result = {'stamp':[VERSION,data['source_sha256'],str(lang),lang.stat().st_mtime_ns if lang else 0],'rows':rows}
    path = folder/('player_display.json' if club is None else f'player_display_{club}.json')
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
    tmp.replace(path)
