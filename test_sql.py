import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import duckdb
import app
from sql_query import build_query, run_query


class SQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / 'fixture.parquet'
        with duckdb.connect() as db:
            db.execute("COPY (SELECT i+42300 AS persona_id, i%3 AS grupo, CASE WHEN i=25 THEN NULL ELSE 'O''Brien; SELECT' END AS nombre, (9007199254740993+i)::BIGINT AS grande FROM range(230) t(i)) TO ? (FORMAT PARQUET)", [str(cls.path)])
        cls.info = app.register(cls.path)
        cls.server = app.ThreadingHTTPServer(('127.0.0.1',0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        app.FILES.pop(cls.info['id'],None)
        cls.tmp.cleanup()

    def query(self, projection='*', clauses='', **extra):
        args = dict(id=self.info['id'],projection=projection,clauses=clauses,**extra)
        req = urllib.request.Request(self.base+'/api/query',data=json.dumps(args).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_filter_projection_precision(self):
        r=self.query('`persona_id`, grande, nombre','WHERE persona_id = 42325')
        self.assertEqual(r['rows'],[['42325','9007199254741018',None]])
        self.assertEqual(r['total'],1)
        self.assertEqual([c['name'] for c in r['columns']],['persona_id','grande','nombre'])

    def test_order_paging(self):
        r=self.query('persona_id','WHERE persona_id >= 42325 ORDER BY persona_id DESC',limit='50',offset='50')
        self.assertEqual((r['total'],len(r['rows']),r['rows'][0][0]),(205,50,'42479'))

    def test_grouping_and_empty(self):
        r=self.query('grupo, COUNT(*) AS cantidad','GROUP BY grupo HAVING COUNT(*) > 70 ORDER BY grupo LIMIT 2')
        self.assertEqual(r['rows'],[['0','77'],['1','77']])
        r=self.query('persona_id','WHERE persona_id = -1')
        self.assertEqual(r['rows'],[])
        self.assertEqual(r['columns'][0]['name'],'persona_id')

    def test_literals_are_not_commands(self):
        r=self.query('COUNT(*) AS total',"WHERE nombre = 'O''Brien; SELECT'")
        self.assertEqual(r['rows'],[['229']])

    def test_rejects_mutations_and_other_sources(self):
        for tail in ['WHERE 1=1; DROP TABLE parquet','WHERE EXISTS (SELECT 1 FROM otra)','JOIN otra ON true','WHERE true -- comment',"WHERE nombre='bad",'WHERE nombre=$$value$$']:
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                build_query('*',tail)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.query('*','WHERE true; DROP TABLE parquet')
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.query('COUNT(*) AS total')['rows'],[['230']])

    def test_other_local_file_access_is_blocked(self):
        secret=Path(self.tmp.name)/'secret.txt'
        secret.write_text('private')
        with app.connect(self.path) as db:
            run_query(db,self.path,{'projection':'COUNT(*) AS total'})
            with self.assertRaises(duckdb.PermissionException):
                db.execute('SELECT * FROM read_text(?)',[str(secret)]).fetchall()

    def test_static_modules(self):
        for filename in ['viewer.js','sql.js']:
            with urllib.request.urlopen(self.base+'/'+filename) as response:
                self.assertEqual(response.status,200)
                self.assertIn('text/javascript',response.headers['Content-Type'])


if __name__ == '__main__':
    unittest.main()
