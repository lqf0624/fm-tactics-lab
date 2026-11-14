"""Read online draft teams by their stored team and player references."""
import struct

from fmsave import _version as version
from fmsave._container import read_section
from fmsave._errors import CorruptSaveError
from fmsave._layouts import ContractLayout, HumansLayout, PersonBlockLayout, SaveSummaryLayout, SummaryStringsLayout, find_layout
from fmsave.readers.player_scan import window_end
from fmsave.readers.players import build_player_decoder
from fmsave.readers.tactics import MISSING_REFERENCE, _next_signature, _read_routines, _read_selection_part, _stored_block_starts, find_tactics_layout, walk_tactic_blocks


def _schema(container, name, data):
    return version.section_schema(data, container.sections[name].extension, name, container.file_name)


def read_summary(container):
    """A draft has zero loaded divisions and a counted list of human entries."""
    section = version.SAVE_SUMMARY_SECTION
    data = version.read_metadata_section(container, section)
    schema = _schema(container, section, data)
    layout = find_layout(SaveSummaryLayout, section, schema, '').layout
    build = version.find_game_version(data, layout, container.file_name)
    if schema != 31 or build.build != '27.0.1+2503222':
        return None
    layout = find_layout(SaveSummaryLayout, section, schema, build.build).layout
    try:
        offset = layout.structured_strings_offset
        setup, offset = version.read_length_prefixed_string(data, offset, layout.max_setup_string_bytes)
        stored, offset = version.read_length_prefixed_string(data, offset, layout.max_version_bytes)
        if setup or stored != build.build or version.read_u32(data, offset) != 0:
            return None
        humans = version.read_metadata_section(container, 'humans')
        human_layout = find_layout(HumansLayout, 'humans', _schema(container, 'humans', humans), build.build).layout
        count = struct.unpack_from('<H', humans, human_layout.human_count_offset)[0]
        if not 2 <= count <= 64:
            return None
        offset += 4 + layout.manager_header_bytes
        entries = []
        for _ in range(count):
            manager, offset = version.read_length_prefixed_string(data, offset, layout.max_summary_name_bytes)
            team, offset = version.read_length_prefixed_string(data, offset, layout.max_summary_name_bytes)
            uid = version.read_u32(data, offset)
            offset += layout.club_uid_bytes
            if not manager or not team or uid < 0x70000000:
                return None
            entries.append((uid, manager, team))
        date = version.decode_date(data, offset)
        if date is None or len({uid for uid, _, _ in entries}) != count:
            return None
    except (CorruptSaveError, struct.error):
        return None
    strings = find_layout(SummaryStringsLayout, section, schema, build.build).layout
    return version.SummaryFacts(build, version.read_summary_strings(data, strings),
                                date, version.decode_time_slot(data, offset)), entries


def _team_links(db, entries, team_ids):
    links = {}
    for uid, manager, name in entries:
        # TEAM rows carry the runtime team ID just before the summary's ID.
        key = struct.pack('<I', uid)
        candidates = []
        offset = db.find(key)
        while offset >= 0:
            if offset >= 10 and db[offset - 10:offset - 4] == b'\x00' * 6:
                team_id = struct.unpack_from('<I', db, offset - 4)[0]
                if team_id in team_ids:
                    candidates.append(team_id)
            offset = db.find(key, offset + len(key))
        if len(candidates) != 1 or candidates[0] in links:
            raise ValueError('无法唯一对应选秀球队与存储战术队伍')
        links[candidates[0]] = (uid, manager, name)
    return links


def read_dataset(save, folder, source, digest):
    draft = read_summary(save._container_index)
    if draft is None:
        return None
    _, entries = draft
    from desktop_save_worker import plain, write
    from desktop_save_setpieces import read_team_routines

    info = save.info
    section = read_section(save._container_index, 'tactics_man')
    layout = find_tactics_layout(info.section_schemas['tactics_man'], info.build)
    starts = _stored_block_starts(section, layout, source.name)
    by_team = {struct.unpack_from('<I', section, start)[0]: start for start in starts}
    if len(by_team) != len(starts) or len(starts) != len(entries):
        raise ValueError('选秀球队数量与存储战术区不一致')
    blocks, counts = walk_tactic_blocks(section, sorted(by_team), layout, source.name)
    if counts.blocks_found != len(entries) or counts.tactic_blocks_count_matching != counts.tactic_blocks:
        raise ValueError('选秀存储战术的队伍或方案计数不一致')
    clubs, managed, tactics, selections = [], [], [], []
    rosters, player_index, setpieces = {}, {}, {}
    context = save._context
    schema = info.section_schemas['game_db']
    with context.section('game_db') as db:
        links = _team_links(db, entries, by_team)
        records = context.player_records()
        decoder = build_player_decoder(
            records.layout, context.club_index(), context.name_pools(), info.game_date,
            find_layout(PersonBlockLayout, 'game_db', schema, info.build).layout,
            find_layout(ContractLayout, 'game_db', schema, info.build).layout, source.name,
        )
        fields = ('uid', 'unique_id', 'name', 'team_id', 'positions', 'raw_attributes',
                  'raw_left_foot', 'raw_right_foot', 'height_cm', 'age', 'ability',
                  'personality', 'trait_bits', 'reputation')
        roster_positions = {team_id: [] for team_id in links}
        header = decoder.header_layout
        for position, offset in enumerate(records.record_offsets):
            row = header.struct_object.unpack_from(db, offset + header.start_offset)
            team_id = row[header.team_id_index]
            if team_id in roster_positions:
                roster_positions[team_id].append(position)
        for block in blocks:
            team_id = block.team_id
            uid, manager, name = links[team_id]
            clubs.append({'uid': uid, 'unique_id': uid, 'name': name, 'short_name': name,
                          'nation_id': None, 'teams': [{'team_id': team_id, 'slot': 0}]})
            managed.append({'club_uid': uid, 'club_name': name, 'manager_name': manager,
                            'manager_staff_uid': None})
            players = {}
            for position in roster_positions[team_id]:
                selector = records.pindexes[position] + 1
                player, _ = decoder.decode(db, records.record_offsets[position],
                                           window_end(records, position, len(db)),
                                           is_last_record=position + 1 == len(records.uids),
                                           suspension_entries=None)
                if player.team_id != team_id or player.unique_id is None:
                    continue
                if str(player.unique_id) in player_index:
                    raise ValueError('选秀球员身份重复')
                players[selector] = {field: plain(getattr(player, field)) for field in fields}
                players[selector].update(club_uid=uid, team_club_uid=uid, team_slot=0)
                player_index[str(player.unique_id)] = uid
            if len(players) < 11:
                raise ValueError(f'{name} 不足 11 名已核对的选秀球员')
            rosters[uid] = list(players.values())
            for place, selector in enumerate(block.selection_slots):
                if selector == MISSING_REFERENCE or selector not in players:
                    continue
                player = players[selector]
                selections.append({'club_uid': uid, 'team_id': team_id, 'team_slot': 0,
                                   'slot': place if place < 11 else place - 11, 'substitute': place >= 11,
                                   'player_uid': player['uid'], 'player_name': player['name'],
                                   'source_uid': player['unique_id']})

            start = by_team[team_id]
            end = next((value for value in starts if value > start), len(section))
            selection = _read_selection_part(section, start, end, layout, source.name)
            _, _, tactic_end = _read_routines(section, selection.end, end, layout)
            cursor = selection.end
            for index, tactic in enumerate(block.tactics):
                at, _ = _next_signature(section, cursor, tactic_end, layout)
                if at is None:
                    raise ValueError('选秀战术记录边界缺失')
                cursor = at + len(layout.user_signature)
                after, _ = _next_signature(section, cursor, tactic_end, layout)
                item = {'club_uid': uid, 'club_name': name, 'team_id': team_id, 'team_slot': 0,
                        'index': index, 'name': tactic.name, 'slots': plain(tactic.slots)}
                if tactic.walk_complete and tactic.oop_index_permutation:
                    raw_path = folder / f'tactic_{len(tactics)}.bin'
                    raw_path.write_bytes(section[at:after if after is not None else tactic_end])
                    item['raw_plan'] = raw_path.name
                tactics.append(item)
            routines = read_team_routines(section, team_id, layout, source.name, starts)
            if routines:
                setpieces[str(team_id)] = routines
    roster_dir = folder / 'rosters'
    roster_dir.mkdir(exist_ok=True)
    for uid, players in rosters.items():
        write(roster_dir / f'{uid}.json', players)
    write(folder / 'player_index.json', player_index)
    roster_counts = {str(uid): len(players) for uid, players in rosters.items()}
    from desktop_save_compat import PROFILE
    return {'schema': 5, 'save_mode': 'online_draft', 'reader_compatibility_profile': PROFILE,
            'source': str(source), 'source_sha256': digest, 'date': str(info.game_date), 'build': info.build,
            'managed': managed, 'clubs': clubs, 'player_counts': roster_counts, 'first_team_counts': roster_counts,
            'tactics': tactics, 'selections': selections, 'setpieces': setpieces,
            'fixtures': [], 'leagues': [], 'league_clubs': {}, 'competitions': {}, 'nations': {},
            'caches': [], 'warnings': []}
