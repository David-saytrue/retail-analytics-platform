import json
from pathlib import Path
import tempfile
import unittest

from retail import events, generate, money, normalize


class InputTests(unittest.TestCase):
    def test_money_rejects_lossy_values(self):
        for value in ['NaN', 'Infinity', '-1.00', '0.001', '1000000000000', 1.1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)
        self.assertEqual(money('19.9'), '19.90')

    def test_timestamp_requires_timezone(self):
        with self.assertRaises(ValueError):
            normalize('customers', {'id': 1, 'city': 'Tbilisi', 'updated_at': '2026-01-01T00:00:00'})
        with self.assertRaises(ValueError):
            normalize('customers', {'id': True, 'city': 'Tbilisi', 'updated_at': '2026-01-01T00:00:00Z'})

    def test_deterministic_generator_and_conflicting_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generate(root / 'a', 100, 42)
            generate(root / 'b', 100, 42)
            self.assertEqual((root/'a/day1.json').read_bytes(), (root/'b/day1.json').read_bytes())
            batch = root/'a/day1.json'
            self.assertEqual(len(events(batch, root/'a/costs.csv')), 111)
            content = json.loads(batch.read_text())
            content['customers'].append({**content['customers'][0], 'city': 'Kutaisi'})
            batch.write_text(json.dumps(content))
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                events(batch, None)


if __name__ == '__main__':
    unittest.main()
