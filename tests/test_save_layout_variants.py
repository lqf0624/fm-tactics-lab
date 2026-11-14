import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import desktop_save_compat
from desktop_save_setpieces import routine_header_bytes
from fmsave.readers import tactics


class SaveLayoutVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        desktop_save_compat.install()
        cls.layout = tactics.find_tactics_layout(26, '27.0.1+2503222')

    def selection(self, footer, following):
        layout = self.layout
        empty_lists = struct.pack('<I', 0)
        header = struct.pack('<I', 42) + layout.block_marker
        header += struct.pack('<I', 2) + b'XI'
        header += struct.pack('<I', 123) * layout.selection_slot_count
        header += layout.selection_end_marker + empty_lists * 2
        header += bytes([layout.list_item_lead_byte]) + struct.pack('<I', 123)
        header += layout.taker_markers[0] + empty_lists * layout.taker_list_count
        header += layout.order_marker + empty_lists * layout.order_list_count
        return header + footer + following

    def test_extended_selection_requires_tactic_at_declared_boundary(self):
        footer = bytes.fromhex('01 05 01 00 00 00 00 01 00')
        signature = self.layout.alternate_signature
        data = self.selection(footer, signature)
        part = tactics._read_selection_part(data, 0, len(data), self.layout, 'test.fm')
        self.assertEqual(part.tactic_count, 1)
        self.assertEqual(data[part.end:], signature)
        self.assertEqual(part.slots[0], 123)

        bad_footer = self.selection(bytes.fromhex('01 05 02') + footer[3:], signature)
        displaced_tactic = self.selection(footer, b'\0' + signature)
        for data in (bad_footer, displaced_tactic):
            with self.subTest(data=data[-20:]), self.assertRaises(tactics.ReaderCheckError):
                tactics._read_selection_part(data, 0, len(data), self.layout, 'test.fm')

    def test_empty_and_counted_set_piece_headers(self):
        marker = self.layout.routine_area_marker
        prefix = marker + bytes(578 - len(marker))
        record = bytes(24) + b'\x01\x01'
        trailer = b'\0\0\0\0\x3c\0\1\0\0\0'
        zero = prefix + b'\0\0' + trailer
        extended = prefix + b'\x02\0' + record * 2 + trailer
        self.assertEqual(routine_header_bytes(zero, 0, len(zero), self.layout), 590)
        self.assertEqual(routine_header_bytes(extended, 0, len(extended), self.layout), 642)
        bad = bytearray(extended)
        bad[604] = 2
        self.assertEqual(routine_header_bytes(bad, 0, len(bad), self.layout), 590)
