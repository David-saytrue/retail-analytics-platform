"""Immutable file inbox orchestration; business transactions remain in retail.py."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import retail


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ready_batches(inbox: Path) -> list[str]:
    if not inbox.exists():
        return []
    return sorted(p.name for p in inbox.iterdir()
                  if not p.name.startswith('.') and p.is_dir() and not p.is_symlink()
                  and (p / 'READY.json').is_file())


def batch_files(inbox: Path, name: str) -> tuple[Path, Path | None]:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name):
        raise ValueError('Invalid batch directory name')
    root = inbox.resolve()
    directory = inbox / name
    if directory.is_symlink() or directory.resolve().parent != root:
        raise ValueError('Batch directory must stay inside the inbox')
    batch, marker, costs = directory/'batch.json', directory/'READY.json', directory/'costs.csv'
    for file in (batch, marker, costs):
        if file.is_symlink():
            raise ValueError('Inbox files cannot be symlinks')
    manifest = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or set(manifest) != {'batch_sha256', 'costs_sha256'}:
        raise ValueError('Invalid READY.json manifest')
    if digest(batch) != manifest['batch_sha256']:
        raise ValueError(f'{name}: batch checksum mismatch')
    expected_costs = manifest['costs_sha256']
    if (digest(costs) if costs.exists() else None) != expected_costs:
        raise ValueError(f'{name}: costs checksum mismatch')
    return batch, costs if costs.exists() else None


def publish_batches(inbox: Path, names: list[str]) -> dict:
    # Validate every ready file before starting database writes. A valid package
    # must remain immutable after publication; READY.json is published last.
    files = [batch_files(inbox, name) for name in names]
    for batch, costs in files:
        retail.events(batch, costs)
    new_versions = 0
    for batch, costs in files:
        result = json.loads(retail.load(batch, costs))
        new_versions += result['new_versions']
    return {'batches': len(files), 'new_versions': new_versions}


def validate_and_report(reports: Path) -> dict:
    retail.psql((retail.ROOT/'sql/03_checks.sql').read_text(encoding='utf-8'))
    totals = json.loads(retail.psql("""
        SELECT json_build_object(
            'net_revenue', coalesce(sum(net_revenue), 0)::text,
            'gross_profit', coalesce(sum(gross_profit), 0)::text,
            'orders', count(DISTINCT order_id)) FROM mart.sales_line;
    """))
    result = {'validated_at_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'success', 'currency': 'GEL', **totals}
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=reports,
                                     prefix='.report-', suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(result, stream, indent=2)
        stream.write('\n')
    try:
        os.replace(temporary, reports/'latest.json')
    finally:
        temporary.unlink(missing_ok=True)
    return result


def prepare_demo(inbox: Path) -> None:
    """Publish three deterministic demo packages; never replace existing input."""
    inbox.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        generated = Path(temp)
        retail.generate(generated)
        for name, filename, has_costs in [('01-sales', 'day1.json', True),
                                          ('02-return', 'day2.json', False),
                                          ('03-correction', 'day3-correction.json', False)]:
            destination = inbox/name
            if destination.exists():
                batch, costs = batch_files(inbox, name)
                if batch.read_bytes() != (generated/filename).read_bytes() or (
                        has_costs and (costs is None or costs.read_bytes() != (generated/'costs.csv').read_bytes())):
                    raise ValueError(f'{name}: existing demo package differs; preserved without changes')
                continue
            with tempfile.TemporaryDirectory(prefix='.preparing-', dir=inbox) as staging:
                stage = Path(staging)
                (stage/'batch.json').write_bytes((generated/filename).read_bytes())
                if has_costs:
                    (stage/'costs.csv').write_bytes((generated/'costs.csv').read_bytes())
                manifest = {'batch_sha256': digest(stage/'batch.json'),
                            'costs_sha256': digest(stage/'costs.csv') if has_costs else None}
                (stage/'READY.json').write_text(json.dumps(manifest)+'\n', encoding='utf-8')
                # The staging directory itself stays for TemporaryDirectory cleanup.
                destination.mkdir()
                for filename_to_move in ('batch.json', 'costs.csv', 'READY.json'):
                    if (stage/filename_to_move).exists():
                        (stage/filename_to_move).rename(destination/filename_to_move)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare-demo', 'run'])
    parser.add_argument('--inbox', type=Path, default=retail.ROOT/'data/inbox')
    parser.add_argument('--reports', type=Path, default=retail.ROOT/'data/reports')
    args = parser.parse_args()
    if args.command == 'prepare-demo':
        prepare_demo(args.inbox)
        print('Demo packages prepared without replacing existing input')
    else:
        names = ready_batches(args.inbox)
        if not names:
            print('No ready packages; no database writes')
            return
        print(json.dumps(publish_batches(args.inbox, names)))
        print(json.dumps(validate_and_report(args.reports)))


if __name__ == '__main__':
    main()
