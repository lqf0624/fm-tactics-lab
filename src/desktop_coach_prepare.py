"""One static game_db read for league coaches only; no match cache or players."""
import hashlib,json,struct,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).with_name('vendor')))

PROFILE = 'static-first-team-coaches-v6'
LEAGUE_PROFILE = 'static-league-coaches-v5'
FRAGMENT_DIRECTORY = 'first_team_staff_fragments'
MANAGER_JOB = 16
EMPTY_REFERENCES = (0, 0xffffffff)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def _registry(index, wanted):
    """The league club index's minimal club records for a selection."""
    league_clubs = index.get('league_clubs') if isinstance(index.get('league_clubs'), dict) else {}
    rows = []
    for club_uid in sorted({int(value) for value in wanted}):
        row = league_clubs.get(str(club_uid))
        if not isinstance(row, dict):
            raise ValueError('联赛球队索引缺少所选球队，请重新读取存档')
        team_id = row.get('first_team_id')
        if type(team_id) is not int:
            raise ValueError('联赛球队一线队索引不完整')
        rows.append({'uid': club_uid, 'name': row.get('name') or str(club_uid),
                     'short_name': row.get('short_name') or row.get('name') or str(club_uid),
                     'nation_id': row.get('nation_id'),
                     'teams': [{'team_id': team_id, 'slot': 0}]})
    if not rows:
        raise ValueError('联赛没有可读取的球队')
    return rows


def _contract_staff(save, reader, db):
    """Recover save-local selectors for contracts decoded by the staff reader."""
    headers = {}
    original = reader._PersonObject
    def capture(*args, **kwargs):
        person = original(*args, **kwargs)
        headers[person.uid] = (struct.unpack_from('<I', db, person.header)[0] + 1, person.unique_id)
        return person
    reader._PersonObject = capture
    try:
        staff = list(save.staff())
    finally:
        reader._PersonObject = original
    return staff, headers


def _vacancy_candidate(staff, club_uid, team_id, date):
    active = [row for row in staff if row.club_uid == club_uid and row.team_id == team_id
              and row.team_slot == 0 and row.has_contract and not row.is_human_manager
              and row.contract_start is not None and row.contract_start <= date
              and (row.contract_end is None or date <= row.contract_end)]
    managers = {row.uid:row for row in active if getattr(row.job, 'raw', None) == MANAGER_JOB}
    if len(managers) > 1:
        raise ValueError('主教练栏为空，有多份有效一线队主教练合同，无法唯一选择')
    if not managers:
        raise ValueError('主教练栏为空，未找到有效的一线队主教练合同')
    return next(iter(managers.values())), 'manager_contract'


def _referenced_coach(reader, db, selector, records, layout):
    """Resolve a TEAM's one-based person reference against complete staff records."""
    if selector in EMPTY_REFERENCES:
        raise ValueError('存档中的一线队主教练位置为空')
    person_id = selector - 1
    lower, upper = reader._bracket_window(db, person_id, records)
    needle = struct.pack('<I', person_id)
    header_reader = reader._header_reader(layout)
    ceiling = upper if upper < len(db) else None
    match = None
    hit = db.find(needle, lower, upper)
    while hit >= 0:
        identity = reader._header_values(db, hit, header_reader, layout)
        if identity is not None and identity[1] == layout.staff_kind:
            block, slots_ok, _, further_ok = reader._read_ability_block(db, hit, layout)
            if block is not None and slots_ok and further_ok:
                closing = reader._closing_header(db, person_id, hit, identity[0], ceiling, layout)
                if closing is not None:
                    if match is not None:
                        raise ValueError('同一主教练引用对应多条完整职员记录，无法确认身份')
                    match = hit, identity[0], closing
        hit = db.find(needle, hit + 1, upper)
    if match is None:
        raise ValueError('一线队有主教练引用，但职员身份或战术偏好未通过校验')
    return match


def prepare(source, folder, index_path, selection_path=None):
    import desktop_save_compat
    desktop_save_compat.install()
    import fmsave
    import fmsave.readers.staff as reader
    from desktop_generation_team_table import from_save
    from desktop_opponent_scope import identify
    from desktop_storage import bounded_output
    source = Path(source)
    folder = Path(folder)
    bounded_output(folder)
    folder.mkdir(exist_ok=True)
    index = _read(index_path)
    started = time.monotonic()

    def progress(text):
        (folder / 'progress.json').write_text(json.dumps({'stage': text}, ensure_ascii=False), encoding='utf8')

    progress('核对当前存档，准备读取同联赛教练')
    before = source.stat()
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != index['source_sha256']:
        raise ValueError('存档已更新，请重新读取存档')
    profile = LEAGUE_PROFILE if selection_path is not None else PROFILE
    if selection_path is not None:
        clubs = _registry(index, [c['uid'] for c in _read(selection_path)['clubs']])
    else:
        own = index['managed'][0]['club_uid']
        scope = identify(index, own)
        if scope['league'] is None:
            raise ValueError('当前存档同联赛范围尚未识别')
        wanted = set(scope['league']['club_uids'])
        clubs = [c for c in index['clubs'] if c['uid'] in wanted]
    with fmsave.open(source) as save:
        with save._context.section('game_db') as db:
            progress('读取同联赛球队与现任主教练引用')
            first_team_ids = {t['team_id'] for c in clubs for t in c['teams'] if t['slot'] == 0}
            table = from_save(save, db, first_team_ids)
            records = save._context.player_records()
            layouts = reader.find_staff_layouts(save.info.section_schemas, save.info.build)
            layout = layouts.staff
            decoder = reader.build_person_block_decoder(layouts.person_blocks, save._context.name_pools(),
                save._context.club_index(), save.info.game_date, save.info.file_name)
            staff = []
            rows = []
            failures = []
            fragments = folder / FRAGMENT_DIRECTORY
            fragments.mkdir(exist_ok=True)
            managed = {m['club_uid'] for m in index['managed']}
            contract_staff = None
            for team in table['records']:
                club = next(c for c in clubs if any(t['team_id'] == team['team_id'] for t in c['teams']))
                selector = team['coach_person_reference']
                if club['uid'] in managed:
                    continue
                progress('定向读取同联赛教练 ' + str(len(rows) + 1) + ' / ' + str(len(table['records']) - len(managed)))
                assignment = 'first_team_reference'
                candidate = None
                try:
                    if selector in EMPTY_REFERENCES:
                        if contract_staff is None:
                            contract_staff, headers = _contract_staff(save, reader, db)
                        candidate, assignment = _vacancy_candidate(contract_staff, club['uid'], team['team_id'], save.info.game_date)
                        entry = headers.get(candidate.uid)
                        if entry is None or not candidate.name or candidate.unique_id is None or entry[1] != candidate.unique_id:
                            raise ValueError('一线队职员合同身份未通过核对')
                        selector = entry[0]
                    header, uid, closing = _referenced_coach(reader, db, selector, records, layout)
                    if candidate and (candidate.uid != uid or candidate.unique_id != closing[1]):
                        raise ValueError('一线队职员合同与偏好记录的身份不符')
                except ValueError as error:
                    failures.append({'club_uid': club['uid'], 'selector': selector, 'error': str(error)})
                    continue
                lo, hi = reader._person_block_window(db, header, None, closing[0], layout)
                person = decoder.decode(db, lo, hi)
                if person is None:
                    person = decoder.decode(db, header + layout.kind_offset, closing[0])
                base = header + layout.ability_base_offset + layout.entry_bytes * db[header + layout.entry_count_offset]
                start = base + layout.preferences_offset
                end = base + layout.block_40_offset + layout.block_40_count
                if end - start != 52:
                    raise ValueError('教练偏好结构大小变化')
                raw = bytes(db[header + 13:end + 4096])
                (fragments / f'{selector}.bin').write_bytes(raw)
                rows.append({'person_selector': selector, 'profile_hex': bytes(db[start:end]).hex(),
                             'codes_hex': bytes(db[base + layout.codes_offset:
                                                  base + layout.codes_offset + layout.code_count]).hex(),
                             'ability_and_reputation_words': list(struct.unpack_from('<5H', db, base - 6))})
                staff.append({'person_selector': selector, 'uid': uid, 'unique_id': closing[1],
                              'name': candidate.name if candidate else (person[reader._PERSON_NAME] if person else str(closing[1])),
                              'team_id':team['team_id'], 'coach_assignment':assignment,
                              'club_uid': club['uid'], 'is_human_manager': False})
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('读取期间存档发生变化')
    table['source_sha256'] = digest
    result = {'profile': profile, 'source_sha256': digest, 'date': index['date'], 'clubs': clubs,
              'staff': staff, 'failures': failures, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'no_match_cache_read': True}
    for name, value in [('source_team_table.json', table),
                        ('staff_fragments.json', {'source_sha256': digest, 'rows': rows}),
                        ('inputs.json', result)]:
        (folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
    progress('教练静态读取完成，核对原版读回与原装预设')
    return {'coaches': len(rows), 'failures': failures, 'elapsed_seconds': result['elapsed_seconds']}

if __name__ == '__main__':
    print(json.dumps(prepare(*sys.argv[1:]), ensure_ascii=False), flush=True)
