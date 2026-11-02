import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline import batch_files, prepare_demo, publish_batches, ready_batches


class InboxTests(unittest.TestCase):
    def test_incomplete_package_is_not_discovered_and_demo_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            inbox = Path(temp)
            (inbox/'incomplete').mkdir()
            (inbox/'incomplete/batch.json').write_text('{}')
            self.assertEqual(ready_batches(inbox), [])
            prepare_demo(inbox)
            before = {str(f.relative_to(inbox)): f.read_bytes() for f in inbox.rglob('*') if f.is_file()}
            prepare_demo(inbox)
            self.assertEqual(before, {str(f.relative_to(inbox)): f.read_bytes() for f in inbox.rglob('*') if f.is_file()})
            self.assertEqual(ready_batches(inbox), ['01-sales', '02-return', '03-correction'])

    def test_corrupt_later_package_prevents_any_database_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            inbox = Path(temp)
            prepare_demo(inbox)
            (inbox/'03-correction/batch.json').write_text('{}')
            with patch('retail.load') as load:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    publish_batches(inbox, ready_batches(inbox))
                load.assert_not_called()

    def test_path_traversal_and_changed_demo_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            inbox = Path(temp)
            prepare_demo(inbox)
            for name in ['../outside', '/tmp/outside', '..', 'a/b']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    batch_files(inbox, name)
            file = inbox/'01-sales/batch.json'
            file.write_text(json.dumps({'customers': []}))
            with self.assertRaises(ValueError):
                prepare_demo(inbox)
            self.assertEqual(json.loads(file.read_text()), {'customers': []})


if __name__ == '__main__':
    unittest.main()
