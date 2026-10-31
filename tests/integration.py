"""Run against an EMPTY, dedicated database. Never resets or deletes data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retail import generate, initialize, load, psql


@unittest.skipUnless(os.environ.get('RETAIL_TEST_DB') == '1', 'Set RETAIL_TEST_DB=1 for a disposable DB')
class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if psql("SELECT count(*) FROM information_schema.schemata "
                "WHERE schema_name IN ('ops','raw','staging','dwh','mart');") != '0':
            raise RuntimeError('Integration tests require an empty dedicated database')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        generate(cls.root)
        initialize()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def batch(self, name, content):
        path = self.root / name
        path.write_text(json.dumps(content), encoding='utf-8')
        return path

    def totals(self):
        return psql('SELECT sum(net_revenue), sum(gross_profit) FROM mart.sales_line;')

    def test_end_to_end(self):
        first = json.loads(load(self.root/'day1.json', self.root/'costs.csv'))
        self.assertEqual(first['new_versions'], 11)
        self.assertEqual(self.totals(), '260.00|108.00')
        self.assertEqual(psql('SELECT count(*), count(DISTINCT order_id) FROM mart.sales_line;'), '3|2')
        repeated = json.loads(load(self.root/'day1.json', self.root/'costs.csv'))
        self.assertEqual(repeated['new_versions'], 0)
        self.assertEqual(self.totals(), '260.00|108.00')

        load(self.root/'day2.json')
        self.assertEqual(self.totals(), '170.00|78.00')
        self.assertEqual(psql("SELECT net_revenue FROM mart.daily_finance WHERE event_date='2026-01-02';"), '-90.00')
        self.assertEqual(json.loads(load(self.root/'day2.json'))['new_versions'], 0)
        load(self.root/'day3-correction.json')
        self.assertEqual(self.totals(), '190.00|98.00')
        load(self.root/'day1.json')  # Out-of-order old batch must not revert correction.
        self.assertEqual(self.totals(), '190.00|98.00')

        # The cost effective AFTER sale must not rewrite historical profit.
        cost_file = self.root/'future-cost.csv'
        cost_file.write_text('product_id,effective_from,unit_cost,updated_at\n'
                             '1,2026-01-02,99.00,2026-01-04T12:00:00Z\n')
        empty = self.batch('empty.json', {})
        load(empty, cost_file)
        self.assertEqual(self.totals(), '190.00|98.00')

        second_return = {'id': 2, 'line_id': 1, 'date': '2026-01-02', 'quantity': 1,
                         'updated_at': '2026-01-04T12:00:00Z'}
        load(self.batch('second-return.json', {'returns': [second_return]}))
        self.assertEqual(self.totals(), '100.00|68.00')
        self.assertEqual(psql('SELECT count(*) FROM mart.sales_line;'), '3')
        snapshot = psql('SELECT count(*) FROM raw.events;')

        # Invalid data fails after raw insertion and model writes: ALL must roll back.
        invalid_batches = [
            {'returns': [{**second_return, 'id': 3}]},  # Too many returned units.
            {'returns': [{**second_return, 'id': 3, 'line_id': 999}]},
            {'returns': [{**second_return, 'id': 3, 'line_id': 3, 'date': '2025-01-01'}]},
            {'sales': [{**json.loads((self.root/'day1.json').read_text())['sales'][0],
                        'customer_id': 999, 'updated_at': '2026-01-05T12:00:00Z'}]},
            {'customers': [{'id': 1, 'city': 'Other', 'updated_at': '2026-01-01T12:00:00Z'}]},
            {'sales': [{**json.loads((self.root/'day1.json').read_text())['sales'][0],
                        'date': '2024-01-01', 'updated_at': '2026-01-05T12:00:00Z'}]},
            {'sales': [{**json.loads((self.root/'day1.json').read_text())['sales'][0],
                        'customer_id': 2, 'updated_at': '2026-01-05T12:00:00Z'}]},
        ]
        for i, batch in enumerate(invalid_batches):
            with self.subTest(invalid=i):
                with self.assertRaises(RuntimeError):
                    load(self.batch(f'invalid-{i}.json', batch))
                self.assertEqual(psql('SELECT count(*) FROM raw.events;'), snapshot)
                self.assertEqual(self.totals(), '100.00|68.00')
        self.assertEqual(psql("SELECT count(*) FROM ops.runs WHERE status='failed';"), '7')
        load(empty)  # Recovery succeeds without a reset.

        # A one-cent line returned in three pieces must refund exactly one cent.
        line = {**json.loads((self.root/'day1.json').read_text())['sales'][2],
                'id': 4, 'order_id': 3, 'unit_price': '0.01', 'discount': '0.02'}
        returns = [dict(id=i+10, line_id=4, date='2026-01-02', quantity=1,
                        updated_at='2026-01-05T12:00:00Z') for i in range(3)]
        load(self.batch('rounding.json', {'sales': [line], 'returns': returns}))
        self.assertEqual(psql('SELECT sum(refund) FROM dwh.fact_returns WHERE line_id=4;'), '0.01')
        self.assertEqual(self.totals(), '100.00|68.00')
        psql((Path(__file__).resolve().parents[1]/'sql/03_checks.sql').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
