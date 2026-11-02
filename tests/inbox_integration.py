"""Real PostgreSQL inbox regression checks, only in an empty dedicated database."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retail
from pipeline import digest, prepare_demo, publish_batches, ready_batches, validate_and_report


@unittest.skipUnless(os.environ.get('RETAIL_TEST_DB') == '1', 'Requires a dedicated test DB')
class InboxDatabaseTests(unittest.TestCase):
    def test_replay_and_financial_report(self):
        self.assertEqual(retail.psql("SELECT count(*) FROM information_schema.schemata "
                                     "WHERE schema_name IN ('ops','raw','staging','dwh','mart');"), '0',
                         'Requires an empty dedicated test database; nothing is reset')
        with tempfile.TemporaryDirectory() as temp:
            inbox, reports = Path(temp)/'inbox', Path(temp)/'reports'
            prepare_demo(inbox)
            self.assertEqual(publish_batches(inbox, ready_batches(inbox)),
                             {'batches': 3, 'new_versions': 13})
            first = validate_and_report(reports)
            self.assertEqual((first['net_revenue'], first['gross_profit'], first['orders']),
                             ('190.00', '98.00', 2))
            self.assertEqual(publish_batches(inbox, ready_batches(inbox)),
                             {'batches': 3, 'new_versions': 0})
            second = validate_and_report(reports)
            for key in ('net_revenue', 'gross_profit', 'orders'):
                self.assertEqual(first[key], second[key])
            self.assertEqual(json.loads((reports/'latest.json').read_text()), second)
            # A well-formed package can still fail SQL business checks. Its raw
            # versions and facts roll back; the last report remains historical.
            previous_report = (reports/'latest.json').read_bytes()
            bad = inbox/'04-invalid-return'
            bad.mkdir()
            (bad/'batch.json').write_text(json.dumps({'returns': [
                {'id': 500, 'line_id': 1, 'date': '2026-01-02', 'quantity': 99,
                 'updated_at': '2026-01-04T12:00:00Z'}]}))
            (bad/'READY.json').write_text(json.dumps({
                'batch_sha256': digest(bad/'batch.json'), 'costs_sha256': None}))
            with self.assertRaises(RuntimeError):
                publish_batches(inbox, ready_batches(inbox))
            self.assertEqual(retail.psql('SELECT sum(net_revenue), sum(gross_profit) FROM mart.sales_line;'),
                             '190.00|98.00')
            self.assertEqual(retail.psql("SELECT count(*) FROM ops.runs WHERE status='failed';"), '1')
            self.assertEqual((reports/'latest.json').read_bytes(), previous_report)
            # Quarantine rejected input, then retry all accepted packages.
            bad.rename(inbox/'.quarantine-04-invalid-return')
            self.assertEqual(publish_batches(inbox, ready_batches(inbox))['new_versions'], 0)
            self.assertEqual(validate_and_report(reports)['net_revenue'], '190.00')


if __name__ == '__main__':
    unittest.main()
