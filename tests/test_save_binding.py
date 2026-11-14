"""Save transitions must never transfer personal instructions to reused IDs."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import desktop_save_mode as saves
import desktop_static_plans as plans


def neutral():
    return dict(press=0, mark=0, tackle=0, foot=0, personal=False)


class SaveBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'rosters').mkdir()
        people = [dict(unique_id=i, club_uid=680, team_slot=0, name=f'Player {i}',
                       positions={'stc':20}, ability={'current':100}) for i in range(1, 12)]
        (self.folder / 'rosters/680.json').write_text(json.dumps(people), encoding='utf8')
        data = {'clubs':[{'uid':680,'name':'Club'}], 'selections':[], 'date':'2028-04-08',
                'tactics':[{'club_uid':680,'team_slot':0,'team_id':1,'name':'Saved tactic'}]}
        (self.folder / 'dataset.json').write_text(json.dumps(data), encoding='utf8')
        app = SimpleNamespace(validate_scenario=copy.deepcopy, integer=lambda v,*_:int(v), TAKER_KEYS=[])
        self.lib = SimpleNamespace(app=app, folder=lambda _:self.folder, ensure_rosters=lambda *_:None,
                                   player_values=lambda p:([50],{}), parsed_plan=lambda *_:{},
                                   apply_plan=lambda *_:None, select_squad=lambda s,*a,**kw:s)
        tree = ast.parse((ROOT / 'src/fm27_tactics_server.py').read_text('utf8'))
        node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='match_opposition')
        ns = {'unpack_oi':lambda _:neutral()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<match_opposition>','exec'),ns)
        self.match = ns['match_opposition']

    def team(self, key):
        team = {'name':'Club','players':[{'source_uid':i,'name':str(i)} for i in range(1,24)],
                'lineup':list(range(11)), 'roster_size':23,
                'phases':[[{'position':'ST','instructions':{}} for _ in range(11)] for _ in range(2)],
                'setpieces':{'role_priorities':{}},
                'opposition':{'players':[neutral() for _ in range(23)],'positions':{'ST':{'press':2}},
                              'by_player_uid':{'999':{**neutral(),'press':2,'personal':True}}}}
        if key is not None:team['roster_source']={'id':key,'club_uid':680}
        return team

    def load(self, route, old_key, key):
        original = self.team(old_key)
        scenario = {'teams':[copy.deepcopy(original),self.team(old_key)]}
        if route=='static':
            result=plans.roster(self.lib,key,680,scenario['teams'][0])
        elif route=='board':
            result=saves.SaveLibrary.board_roster(self.lib,key,680,0,scenario)
        else:
            result=saves.SaveLibrary.load_team(self.lib,key,680,0,list(range(1,12)),0,scenario)['scenario']['teams'][0]
        return result

    def test_new_or_unknown_save_cannot_apply_old_uid_override(self):
        for route in ('static','board','stored'):
            for old_key in ('old-save',None):
                with self.subTest(route=route,old_key=old_key):
                    owner=self.load(route,old_key,'new-save')
                    self.assertEqual(owner['roster_source']['id'],'new-save')
                    self.match(owner,{'players':[]},{'players':[{'source_uid':999}]},'new-save')
                    self.assertEqual(owner['opposition']['players'][0],neutral())
                    self.assertEqual(owner['opposition']['positions']['ST']['press'],2)

    def test_same_save_keeps_valid_uid_override(self):
        for route in ('static','board','stored'):
            with self.subTest(route=route):
                owner=self.load(route,'same-save','same-save')
                self.match(owner,{'players':[]},{'players':[{'source_uid':999}]},'same-save')
                self.assertEqual(owner['opposition']['players'][0]['press'],2)
                self.assertTrue(owner['opposition']['players'][0]['personal'])

    def test_match_preparation_rejects_overrides_from_another_save(self):
        owner=self.team('old-save')
        self.match(owner,{'players':[]},{'players':[{'source_uid':999}]},'new-save')
        self.assertEqual(owner['opposition']['players'][0],neutral())
