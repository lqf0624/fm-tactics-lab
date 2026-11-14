import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from datetime import date
from desktop_coach_prepare import _referenced_coach, _vacancy_candidate


class ReferencedCoachTests(unittest.TestCase):
    def resolve(self, valid_blocks, closed):
        # Every candidate repeats the same staff reference. Only complete bodies
        # with matching closing identities may disambiguate the team reference.
        db = (struct.pack("<I", 75) + bytes(12)) * 3
        reader = SimpleNamespace(
            _bracket_window=lambda *_: (0, len(db)),
            _header_reader=lambda _: None,
            _header_values=lambda _, offset, *_rest: (100 + offset, 1),
            _read_ability_block=lambda _, offset, _layout: (
                object() if offset in valid_blocks else None, True, True, True),
            _closing_header=lambda _, person, offset, uid, *_rest: (
                (offset + 12, uid + 1) if offset in closed else None),
        )
        return _referenced_coach(reader, db, 76, None, SimpleNamespace(staff_kind=1))

    def test_duplicate_reference_with_one_complete_staff_body(self):
        self.assertEqual(self.resolve({16, 32}, {0, 32}), (32, 132, (44, 133)))

    def test_rejects_multiple_complete_records(self):
        with self.assertRaisesRegex(ValueError, "多条完整"):
            self.resolve({0, 32}, {0, 32})

    def test_rejects_record_without_verified_identity(self):
        with self.assertRaisesRegex(ValueError, "未通过校验"):
            self.resolve({16}, {0, 32})

class VacancyTests(unittest.TestCase):
    today = date(2028, 4, 1)

    def staff(self, uid, job, **changes):
        fields = dict(uid=uid, club_uid=713, team_id=588, team_slot=0, has_contract=True,
                      is_human_manager=False, job=SimpleNamespace(raw=job),
                      contract_start=date(2026, 1, 4), contract_end=date(2029, 6, 30))
        return SimpleNamespace(**{**fields, **changes})

    def test_first_team_manager_precedes_assistant(self):
        rows = [self.staff(1, 20), self.staff(2, 16)]
        self.assertEqual(_vacancy_candidate(rows, 713, 588, self.today), (rows[1], 'manager_contract'))

    def test_assistants_do_not_replace_unverified_managers(self):
        rows = [self.staff(1, 20), self.staff(2, 16, team_slot=1), self.staff(3, 16, team_id=111),
                self.staff(4, 16, contract_start=date(2028, 4, 8)), self.staff(5, 16, contract_end=date(2028, 3, 1))]
        with self.assertRaisesRegex(ValueError, '未找到有效'):
            _vacancy_candidate(rows,713,588,self.today)
        with self.assertRaisesRegex(ValueError, '多份'):
            _vacancy_candidate(rows+[self.staff(6, 16),self.staff(7, 16)],713,588,self.today)
        with self.assertRaisesRegex(ValueError, '未找到有效'):
            _vacancy_candidate(rows[1:],713,588,self.today)
