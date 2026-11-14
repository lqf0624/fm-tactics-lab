"""Observed FM27 save layouts; extends exact registrations, never disables checks.

Supported saves: 27.0.0+2486695, 27.0.0+2493426, 27.0.1+2494687 and 27.0.1+2503222.
The later builds use summary/game/humans/tactics schemas 31/47/24/26. Plan flag 2 also occurs
in native standalone FMF plans, and does not change the slot layout.
Nonempty counted secondary slot maps are walked without changing native bytes.
This adapter is installed only inside the private save-reader process.
"""
from dataclasses import replace
from pathlib import Path
import sys

PROFILE = 'fm27-save-2486695-2503222-v11'
LATER_BUILDS = ('27.0.0+2493426', '27.0.1+2494687', '27.0.1+2503222')
FRAME_DECOMPRESSED_CAP = 768 * 1024**2
TOTAL_DECOMPRESSED_CAP = 1536 * 1024**2


def install():
    vendor = Path(__file__).with_name('vendor')
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    from fmsave import _layouts, _version
    from fmsave._layouts import GameInfoLayout, StaffLayout, TacticsLayout
    if getattr(_layouts,'_fm27_desktop_profile',None)==PROFILE:
        return
    _version.FM27_FRAME_DECOMPRESSED_CAP = FRAME_DECOMPRESSED_CAP
    _version.FM27_TOTAL_DECOMPRESSED_CAP = TOTAL_DECOMPRESSED_CAP
    original=_layouts.registered_layouts()
    entries=[]
    for entry in original:
        if entry.build!='27.0.0+2486695':
            entries.append(entry)
            continue
        layout=entry.layout
        if isinstance(layout,TacticsLayout):
            # Keep user flag 0 and preset flag 1; add the observed user flag 2.
            # Named routines share the length-prefixed name field used in FM26.
            layout=replace(layout,alternate_signature=layout.user_signature[:-1]+b'\x02',
                           named_routines_supported=True)
        entries.append(replace(entry,layout=layout))
        if isinstance(layout,GameInfoLayout) and entry.schema==47:
            # Schema 47 in this build places the filename count two bytes later.
            # Empty lists hid the offset error in earlier samples.
            layout=replace(layout,filename_count_offset_after_db_version=167)
        for build in LATER_BUILDS:
            later=layout
            if isinstance(layout,TacticsLayout) and build.startswith('27.0.1+'):
                # The TAC header stores 27.0.1 in the same field that held
                # 27.0.0. Revision 68 and the slot grammar remain unchanged.
                def signature(value):
                    return value[:5]+b'\x01'+value[6:]
                later=replace(layout,user_signature=signature(layout.user_signature),
                              preset_signature=signature(layout.preset_signature),
                              alternate_signature=signature(layout.alternate_signature))
            entries.append(replace(entry,build=build,layout=later))
    registered=tuple(entries)
    _layouts.registered_layouts=lambda:registered
    _install_slot_map_reader(tuple(e.layout for e in registered
                                  if isinstance(e.layout,TacticsLayout)
                                  and e.build in ('27.0.0+2486695', *LATER_BUILDS)))
    _install_tactic_section_reader(tuple(e.layout for e in registered
                                       if isinstance(e.layout,TacticsLayout)
                                       and e.build in LATER_BUILDS))
    _install_staff_code_reader(tuple(e.layout for e in registered
                                    if isinstance(e.layout, StaffLayout)
                                    and e.build in ('27.0.0+2486695', *LATER_BUILDS)))
    read_game_info_facts=_version.read_game_info_facts

    def read_registered_game_info(container, schemas, version, known_build):
        if version.build in LATER_BUILDS and schemas.get('game_info')==47:
            # The cross-build fallback sees two matches when the list is empty.
            # Select the observed build's layout and still check clock and tail.
            layout=_layouts.find_layout(GameInfoLayout,'game_info',47,version.build).layout
            data=_version.read_metadata_section(container,'game_info')
            return _version.checked_game_info_candidate(data,layout,version,container.file_name)
        return read_game_info_facts(container,schemas,version,known_build)

    _version.read_game_info_facts=read_registered_game_info
    from desktop_save_draft import read_summary
    original_summary = _version.read_summary_facts

    def read_registered_summary(container):
        try:
            return original_summary(container)
        except _version.ReaderCheckError:
            draft = read_summary(container)
            if draft is None:
                raise
            return draft[0]

    _version.read_summary_facts = read_registered_summary
    _layouts._fm27_desktop_profile=PROFILE


def _install_tactic_section_reader(layouts):
    from fmsave.readers import tactics
    from desktop_save_setpieces import routine_header_bytes

    read_text = tactics._read_text
    find_signature = tactics._next_signature
    find_starts = tactics._stored_block_starts
    find_club_starts = tactics._block_starts
    read_selection = tactics._read_selection_part
    read_routine_groups = tactics._read_routine_groups

    def text(section, cursor, end, layout, filename, what):
        if layout in layouts and what in ('a tactic style label', 'style'):
            # A customized style label is a bounded UTF-8 string, independent of
            # the shorter team selection label and tactic name fields.
            layout = replace(layout, name_length_range=(layout.name_length_range[0], 16384))
        return read_text(section, cursor, end, layout, filename, what)

    def signature(section, cursor, end, layout):
        offset, is_user = find_signature(section, cursor, end, layout)
        if layout in layouts:
            # The in-save alternate flags are 2 and 3. Both retain the same
            # team instructions, slot grammar and native boundary validation.
            extra = section.find(layout.user_signature[:-1] + b'\x03', cursor, end)
            if extra >= 0 and (offset is None or extra < offset):
                return extra, True
        return offset, is_user

    def selection(section, start, end, layout, filename):
        try:
            return read_selection(section, start, end, layout, filename)
        except tactics.ReaderCheckError:
            if layout not in layouts:
                raise
            return _extended_tactic_selection(tactics, read_selection, section, start, end, layout, filename)

    def routines(section, area, end, layout):
        size = routine_header_bytes(section, area, end, layout) if layout in layouts else layout.routine_area_header_bytes
        return read_routine_groups(section, area + size - layout.routine_area_header_bytes, end, layout)

    def starts(section, layout, filename):
        offsets = find_starts(section, layout, filename)
        if layout not in layouts or not offsets or offsets[0] != layout.first_block_offset:
            return offsets
        selector, count = tactics.read_tactics_header(section, layout, filename)
        if not count or len(offsets) != count * 2:
            return offsets
        # Some saves append a second selection table after the AI preset area.
        # Its repeated manager/count header and team IDs identify the second table.
        duplicate_header = b'\x01\x00\x01\x0d' + selector.to_bytes(4, 'little') + count.to_bytes(4, 'little')
        second = offsets[count]
        if section[second-len(duplicate_header):second] != duplicate_header:
            return offsets
        primary, secondary = offsets[:count], offsets[count:]
        team_ids = lambda rows: [section[start:start+4] for start in rows]
        if team_ids(primary) != team_ids(secondary) or len(set(team_ids(primary))) != count:
            return offsets
        return primary

    def club_starts(section, team_ids, layout):
        result = find_club_starts(section, team_ids, layout)
        if layout in layouts and len(result) < len(team_ids):
            structural = starts(section, layout, 'tactics_man')
            for team_id in team_ids:
                hits = [offset for offset in structural if int.from_bytes(section[offset:offset+4], 'little') == team_id]
                if len(hits) == 1:
                    result[team_id] = hits[0]
        return result

    tactics._read_text = text
    tactics._next_signature = signature
    tactics._read_selection_part = selection
    tactics._read_routine_groups = routines
    tactics._stored_block_starts = starts
    tactics._block_starts = club_starts


def _extended_tactic_selection(reader, read_selection, section, start, end, layout, filename):
    # Schema 26 also stores an extended footer: 01 05 01, then the same
    # uint32 value and uint16 count. The meaning of the extra word is unconfirmed.
    # The existing walker locates the footer after validating the selector lists.
    candidate = read_selection(section, start, end, replace(layout, tactic_count_lead_byte=1), filename)
    footer = candidate.end - 7
    record_start = candidate.end + 2
    extended_tag = b'\x01\x05\x01'
    if section[footer:footer+3] != extended_tag or record_start + len(layout.user_signature) > end:
        raise reader.layout_mismatch(filename, 'unrecognized tactic selection footer', reader.TACTICS_SECTION)
    count = int.from_bytes(section[record_start-2:record_start], 'little')
    signature_at, _ = reader._next_signature(section, record_start, record_start + len(layout.user_signature), layout)
    if not count or count > (end - record_start) // len(layout.user_signature) or signature_at != record_start:
        raise reader.layout_mismatch(filename, 'extended selection footer has no matching tactic records', reader.TACTICS_SECTION)
    # Normalize the header for the descriptive reader only. Native plan and
    # routine bytes keep their offsets and are read directly from the save.
    header = section[start:footer] + bytes([layout.tactic_count_lead_byte]) + section[footer+3:record_start]
    part = read_selection(header, 0, len(header), layout, filename)
    if part.tactic_count != count:
        raise reader.layout_mismatch(filename, 'inconsistent extended tactic count', reader.TACTICS_SECTION)
    return replace(part, end=record_start)


def _install_staff_code_reader(layouts):
    from fmsave.readers import staff
    read_ability = staff._read_ability_block

    def ability(db, header, layout):
        block, slots_ok, codes_ok, further_ok = read_ability(db, header, layout)
        if block is not None and not codes_ok and layout in layouts:
            # As in fmsave 0.9.3+, an entirely zero code list is unset in FM27.
            # Mixed or unknown codes still count against the existing check.
            entries = db[header + layout.entry_count_offset]
            start = header + layout.ability_base_offset + layout.entry_bytes * entries + layout.codes_offset
            codes_ok = not any(db[start:start + layout.code_count])
        return block, slots_ok, codes_ok, further_ok

    staff._read_ability_block = ability


def _install_slot_map_reader(layouts):
    """Walk the counted secondary map before the final eight-byte role flags.

    Native fm27_tactic_player_slot_read reads a uint32 count,
    then count * (uint32 key + uint64 value), after the setting entries.
    The dependency's fixed walk covers only the zero-count form. Keep its
    existing descriptive model and checks; raw native plans retain every map
    entry, and are the sole source of simulated instructions and role flags.
    """
    from fmsave.readers import tactics
    original=getattr(tactics._read_slot_block,'_fm27_original',tactics._read_slot_block)

    def read_slot(section,cursor,record_end,layout,*,with_index_byte):
        if layout not in layouts:
            return original(section,cursor,record_end,layout,with_index_byte=with_index_byte)
        header=len(layout.slot_tag)+4+len(layout.slot_constant)+4
        if cursor<0 or record_end>len(section) or cursor+header>record_end:
            return None
        count=int.from_bytes(section[cursor+header-4:cursor+header],'little')
        if not layout.unit_count_range[0]<=count<=layout.unit_count_range[1]:
            return None
        map_at=cursor+header+count*layout.unit_bytes
        fixed_end=map_at+4+8+int(with_index_byte)
        if fixed_end>record_end:
            return None
        extra=int.from_bytes(section[map_at:map_at+4],'little',signed=True)
        if extra<0 or extra>(record_end-fixed_end)//12:
            return None
        if not extra:
            return original(section,cursor,record_end,layout,with_index_byte=with_index_byte)
        map_end=map_at+4+extra*12
        block_end=fixed_end+extra*12
        # Normalize only this bounded slot for the legacy descriptive decoder;
        # never alter the saved raw plan handed to the native TAC reader.
        normalized=section[cursor:map_at+4]+section[map_end:block_end]
        slot=original(normalized,0,len(normalized),layout,with_index_byte=with_index_byte)
        if slot is None or slot.end!=len(normalized):
            return None
        return replace(slot,end=block_end)

    read_slot._fm27_original=original
    tactics._read_slot_block=read_slot
