"""Exercise the retest HTTP handler without requiring the proprietary engine."""
import ast
import copy
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


class RetestSourceTests(unittest.TestCase):
    def test_retest_keeps_original_fixture_identity_in_saved_summary(self):
        tree=ast.parse((ROOT/'src/fm27_tactics_server.py').read_text('utf8'))
        handler=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
        method=next(n for n in handler.body if isinstance(n,ast.FunctionDef) and n.name=='do_POST')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old_dir=root/'old';old_dir.mkdir()
            native=root/'native';(native/'fixtures').mkdir(parents=True)
            for path in (native/'FM27Simulator.exe',native/'fixtures/match.pkm'):path.write_bytes(b'test fixture')
            snapshot={'teams':[{'name':'Opponent'},{'name':'Own'}]}
            encode=lambda s:json.dumps(s,sort_keys=True).encode()
            variants=('A_2_H','B_0_A')
            for variant in variants:(old_dir/f'{variant}.json').write_text(json.dumps(snapshot),encoding='utf8')
            (old_dir/'provenance.json').write_text(json.dumps({'config_hashes':{v:hashlib.sha256(encode(snapshot)).hexdigest() for v in variants},'seeds':[42,43]}),encoding='utf8')
            old={'id':'old','status':'complete','experiment_type':'save_opponents','_dir':old_dir,
                 'schedule':{v:{'group':v[0],'opponent':'Opponent','opponent_key':'opponent','venue':v[-1],'tested_side':int(v[-1]=='A')} for v in variants}}
            jobs={'old':old}
            ns=dict(json=json,urlparse=urlparse,LOCK=threading.RLock(),JOBS=jobs,hashlib=hashlib,
                    encode_scenario=encode,integer=lambda v,*_:int(v),
                    SAVE_LIBRARY=SimpleNamespace(real_active=False,active=False),validate_scenario=copy.deepcopy,
                    enabled_pool=lambda _:False,worker_limits=lambda:{'recommended':1,'maximum':8},
                    desktop_engine=SimpleNamespace(require_available=lambda _:None),
                    ENGINE_COMPATIBILITY={'resource_fingerprint':'fixture'},ENGINE_DLL_SHA256='fixture',
                    secrets=SimpleNamespace(token_hex=lambda _:str(len(jobs))),RUNS=root/'runs',NATIVE=native,
                    datetime=datetime,phase_inputs=SimpleNamespace(pack=lambda s,_:s),CATALOG={},time=time,copy=copy,
                    experiment_name=lambda n,f:n or f,profiles=SimpleNamespace(CONTROLLED_START={}),
                    persist=lambda job:(job['_dir']/'summary.json').write_text(json.dumps({k:v for k,v in job.items() if not k.startswith('_')}),encoding='utf8'),
                    POOL=SimpleNamespace(submit=lambda *_:None),execute=lambda *_:None)
            exec(compile(ast.Module(body=[method],type_ignores=[]),'<do_POST>','exec'),ns)
            for variant in variants:
                with self.subTest(variant=variant):
                    body=json.dumps({'id':'old','variant':variant,'count':2}).encode()
                    request=SimpleNamespace(path='/api/jobs/retest',headers={'Content-Length':str(len(body))},
                                            rfile=io.BytesIO(body),send=lambda data,status=200:(status,data))
                    status,response=ns['do_POST'](request)
                    self.assertEqual(status,202,response)
                    created=jobs[response['id']]
                    created['status']='complete'
                    summary=json.loads((created['_dir']/'summary.json').read_text('utf8'))
                    self.assertEqual(summary['retest_source'],{'id':'old','variant':variant})
                    self.assertEqual(summary['schedule']['B']['tested_side'],int(variant[-1]=='A'))
                    self.assertEqual(json.loads((created['_dir']/'provenance.json').read_text('utf8'))['seeds'],[44,45])
