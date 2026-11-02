"""Database behavior tests; use a running historian container or DATABASE_URL."""
import copy
from datetime import datetime, timezone
import os
import unittest
import uuid

try:
    import psycopg
    from scada.historian import store
except ModuleNotFoundError:
    psycopg = None


@unittest.skipUnless(psycopg and os.getenv('DATABASE_URL'), 'Requires PostgreSQL DATABASE_URL')
class HistorianTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)
        now = datetime.now(timezone.utc).isoformat()
        self.m = dict(batch_id=str(uuid.uuid4()), sequence=2, timestamp=now,
                      created_at=now, started_at=now, ended_at=None,
                      recipe={'name': 'test snapshot'}, state='HOLD', sim_time=100,
                      tags={'temperature': {'value': 60, 'quality': 'GOOD', 'units': 'degC'}},
                      events=[dict(time=100, previous='HEAT', state='HOLD', reason='')],
                      commands=[dict(request_id='start', timestamp=now, action='start', accepted=True)])

    def tearDown(self):
        self.conn.close()

    def test_duplicates_and_out_of_order_do_not_regress_batch(self):
        with self.conn.transaction():
            store(self.conn, self.m)
            store(self.conn, self.m)
            old = copy.deepcopy(self.m)
            old.update(sequence=1, state='HEAT')
            store(self.conn, old)
            batch = self.conn.execute('SELECT state,last_sequence FROM batches WHERE batch_id=%s',
                                      (self.m['batch_id'],)).fetchone()
            self.assertEqual(batch, ('HOLD', 2))
            for table, expected in [('samples', 2), ('events', 1), ('commands', 1)]:
                result = self.conn.execute(f'SELECT count(*) FROM {table} WHERE batch_id=%s',
                                           (self.m['batch_id'],)).fetchone()[0]
                self.assertEqual(result, expected)
            raise psycopg.Rollback()  # verification leaves no synthetic records

    def test_failed_snapshot_rolls_back_every_table(self):
        broken = copy.deepcopy(self.m)
        broken['events'][0]['reason'] = None  # violate NOT NULL after batch/sample inserts
        with self.assertRaises(psycopg.errors.NotNullViolation):
            store(self.conn, broken)
        for table in ('batches', 'samples', 'events', 'commands'):
            count = self.conn.execute(f'SELECT count(*) FROM {table} WHERE batch_id=%s',
                                      (self.m['batch_id'],)).fetchone()[0]
            self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
