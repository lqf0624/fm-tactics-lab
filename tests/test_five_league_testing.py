import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import desktop_league_testing as leagues
import desktop_test_rounds as rounds
import desktop_opponent_scope

class FiveLeagueTests(unittest.TestCase):
    def test_foreign_league_uses_complete_calendar_catalogue(self):
        d={'date':'2028-04-08','fixtures':[],'leagues':[{'competition_id':51,'stage_id':1,'season':2027,
            'club_uids':[1,2,3,4],'first_date':'2027-08-01','last_date':'2028-05-31','fixture_count':12,'complete':True}]}
        self.assertEqual(desktop_opponent_scope.identify(d,1)['same_league'],{2,3,4})
        d['leagues'][0]['complete']=False
        self.assertFalse(desktop_opponent_scope.identify(d,1)['same_league'])

    def test_manual_starters_keep_substitutes_without_duplicates(self):
        team={'players':[{'source_uid':i}for i in range(26)],'roster_size':23}
        starters=list(range(1,12))
        bench=leagues.bench_for_selection(team,starters)
        self.assertEqual(len(bench),12)
        self.assertFalse(set(bench)&set(starters))
        self.assertEqual(leagues.bench_for_selection(team,starters,[]),[])

    def test_current_members_and_missing_leagues(self):
        data={'competitions':{'7':11,'8':12,'22':32},'leagues':[
            {'key':'old','competition_id':7,'season':2026,'club_uids':[1,2],'first_date':'2026-08-01','last_date':'2027-05-31'},
            {'key':'new','competition_id':7,'season':2027,'club_uids':[2,3],'first_date':'2027-08-01','last_date':'2028-05-31'},
            {'key':'second','competition_id':8,'season':2027,'club_uids':[1,4],'first_date':'2027-08-01','last_date':'2028-05-31'}],
            'date':'2028-04-08'}
        rows=leagues.five_leagues(data)
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[0]['club_uids'],[2,3])
        self.assertEqual(rows[0]['key'],'new')
        self.assertEqual([r['available'] for r in rows],[True,False,False,False,False])
    def test_future_not_preferred_to_current(self):
        d={'competitions':{'7':11},'date':'2028-04-08','leagues':[
            {'key':'current','competition_id':7,'club_uids':[1],'first_date':'2027-08-01','last_date':'2028-05-31'},
            {'key':'future','competition_id':7,'club_uids':[2],'first_date':'2028-08-01','last_date':'2029-05-31'}]}
        self.assertEqual(leagues.five_leagues(d)[0]['key'],'current')

class RoundsTests(unittest.TestCase):
    def test_disjoint_even_counts(self):
        r=rounds.plan(42,4,6)
        self.assertEqual([x['seeds'] for x in r],[[42,43],[44,45,46]])
        self.assertEqual(rounds.round_number(r,44),2)
        self.assertIsNone(rounds.round_number(r,99))
    def test_invalid_counts_and_overflow(self):
        for args in [(42,3,4),(42,4,0),(0xffffffff,2,2),(True,2,2)]:
            with self.subTest(args=args),self.assertRaises(ValueError):rounds.plan(*args)
    def test_neutralize_both_teams(self):
        from copy import deepcopy
        team={'opposition':{'players':[{'press':2,'mark':2,'tackle':3,'foot':1,'personal':True}],'positions':{'ST':{'press':2}},'by_player_uid':{'1':{'mark':2}}},'phases':[[{'instructions':{'14':2,'3':1},'target_player':5}]]}
        s={'teams':[deepcopy(team),deepcopy(team)]}
        rounds.neutralize(s)
        for t in s['teams']:
            self.assertEqual(t['opposition']['players'][0],{'press':0,'mark':0,'tackle':0,'foot':0,'personal':True})
            self.assertNotIn('by_player_uid',t['opposition'])
            self.assertEqual(t['phases'][0][0]['instructions']['14'],0)
            self.assertEqual(t['phases'][0][0]['instructions']['3'],1)
            self.assertEqual(t['phases'][0][0]['target_player'],255)
if __name__=='__main__':unittest.main()
