"""Synthetic retail ingestion. Python standard library + PostgreSQL psql client."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
FIELDS = {
    'customers': {'id', 'city', 'updated_at'},
    'products': {'id', 'name', 'category', 'updated_at'},
    'sales': {'id', 'order_id', 'customer_id', 'product_id', 'date', 'quantity',
              'unit_price', 'discount', 'updated_at'},
    'returns': {'id', 'line_id', 'date', 'quantity', 'updated_at'},
    'costs': {'product_id', 'effective_from', 'unit_cost', 'updated_at'},
}


def literal(value: str) -> str:
    """SQL text literal; callers set standard_conforming_strings=on."""
    if '\x00' in value:
        raise ValueError('NUL is not allowed')
    return "'" + value.replace("'", "''") + "'"


def psql(script: str) -> str:
    executable = os.environ.get('PSQL') or shutil.which('psql')
    if not executable:
        raise RuntimeError('psql not found. Set PSQL to the PostgreSQL client path.')
    # Credentials are inherited through PG* environment variables, never CLI args.
    result = subprocess.run(
        [executable, '-X', '-w', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1'],
        input="SET standard_conforming_strings=on; SET TIME ZONE 'UTC';\n" + script,
        text=True, encoding='utf-8', capture_output=True,
        env={**os.environ, 'PGCLIENTENCODING': 'UTF8', 'PGCONNECT_TIMEOUT': '5'},
    )
    if result.returncode:
        # psql may echo source SQL in CONTEXT; do not persist it in run logs.
        errors = [s.strip() for s in result.stderr.splitlines() if s.startswith('ERROR:')]
        raise RuntimeError(errors[0] if errors else 'psql failed; check connection and permissions')
    return result.stdout.strip()


def money(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('Money must be a decimal string, for example "19.90"')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount >= Decimal('1000000000000'):
            raise ValueError('Money out of range')
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Money requires at most two decimal places')
        return format(amount, '.2f')
    except InvalidOperation as exc:
        raise ValueError('Invalid money') from exc


def normalize(entity: str, row: dict) -> dict:
    if not isinstance(row, dict) or set(row) != FIELDS[entity]:
        raise ValueError(f'{entity}: expected exactly {sorted(FIELDS[entity])}')
    row = dict(row)
    for key, value in row.items():
        if key in {'id', 'order_id', 'customer_id', 'product_id', 'line_id', 'quantity'}:
            if type(value) is not int or not 0 < value <= 2147483647:
                raise ValueError(f'{entity}.{key}: expected a positive integer')
        elif key in {'unit_price', 'discount', 'unit_cost'}:
            row[key] = money(value)
        elif key in {'date', 'effective_from'}:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError(f'{entity}.{key}: expected YYYY-MM-DD')
        elif key == 'updated_at':
            if not isinstance(value, str):
                raise ValueError('updated_at must be an ISO timestamp string')
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError('updated_at must include a timezone')
            row[key] = stamp.astimezone(timezone.utc).isoformat()
        elif not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise ValueError(f'{entity}.{key}: expected nonempty text')
    if entity == 'sales' and Decimal(row['discount']) > row['quantity'] * Decimal(row['unit_price']):
        raise ValueError('Discount exceeds line value')
    return row


def events(batch: Path, costs: Path | None) -> list[dict]:
    source = json.loads(batch.read_text(encoding='utf-8'))
    if not isinstance(source, dict) or set(source) - (set(FIELDS) - {'costs'}):
        raise ValueError('Batch must contain only customers/products/sales/returns arrays')
    if costs:
        with costs.open(encoding='utf-8', newline='') as stream:
            source['costs'] = list(csv.DictReader(stream))
        for row in source['costs']:
            row['product_id'] = int(row['product_id'])
    versions = {}
    for entity, rows in source.items():
        if not isinstance(rows, list):
            raise ValueError(f'{entity}: expected an array')
        for row in rows:
            payload = normalize(entity, row)
            record_id = (f"{payload['product_id']}:{payload['effective_from']}"
                         if entity == 'costs' else str(payload['id']))
            key = (entity, record_id, payload['updated_at'])
            event = dict(entity=entity, record_id=record_id,
                         updated_at=payload['updated_at'], payload=payload)
            if key in versions and versions[key] != event:
                raise ValueError('Conflicting payloads with the same id and updated_at')
            versions[key] = event
    return list(versions.values())


def initialize() -> None:
    psql((ROOT / 'sql/01_schema.sql').read_text(encoding='utf-8'))


def load(batch: Path, costs: Path | None = None) -> str:
    incoming = events(batch, costs)
    initialize()
    run_id = str(uuid4())
    psql(f"INSERT INTO ops.runs(run_id, source_file, status) VALUES "
         f"({literal(run_id)}, {literal(batch.name)}, 'running');")
    data = literal(json.dumps(incoming, ensure_ascii=True))
    script = f"""
BEGIN;
-- Serialize publication to avoid stale materialized facts under concurrent loads.
SELECT pg_advisory_xact_lock(780031);
CREATE TEMP TABLE incoming ON COMMIT DROP AS
SELECT * FROM jsonb_to_recordset({data}::jsonb)
AS x(entity text, record_id text, updated_at timestamptz, payload jsonb);
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM incoming i JOIN raw.events r
        USING (entity, record_id, updated_at) WHERE i.payload <> r.payload
    ) THEN RAISE EXCEPTION 'Conflicting source version: same timestamp, different payload'; END IF;
END $$;
WITH inserted AS (
    INSERT INTO raw.events(entity, record_id, updated_at, payload, first_run_id)
    SELECT entity, record_id, updated_at, payload, {literal(run_id)}::uuid FROM incoming
    ON CONFLICT DO NOTHING RETURNING 1
)
UPDATE ops.runs SET new_versions = (SELECT count(*) FROM inserted)
WHERE run_id = {literal(run_id)};
"""
    script += (ROOT / 'sql/02_model.sql').read_text(encoding='utf-8')
    script += (ROOT / 'sql/03_checks.sql').read_text(encoding='utf-8')
    script += f"""
UPDATE ops.runs SET status='success', finished_at=clock_timestamp()
WHERE run_id={literal(run_id)};
COMMIT;
SELECT json_build_object('run_id', run_id, 'status', status, 'new_versions', new_versions)
FROM ops.runs WHERE run_id={literal(run_id)};
"""
    try:
        output = psql(script)
    except RuntimeError as exc:
        psql(f"UPDATE ops.runs SET status='failed', finished_at=clock_timestamp(), "
             f"error={literal(str(exc))} WHERE run_id={literal(run_id)};")
        raise
    return output.splitlines()[-1]


def generate(output: Path, extra_orders: int = 0, seed: int = 42) -> None:
    if extra_orders < 0:
        raise ValueError('extra-orders must be nonnegative')
    output.mkdir(parents=True, exist_ok=True)
    stamp = '2026-01-01T12:00:00Z'
    day1 = {
        'customers': [{'id': 1, 'city': 'Tbilisi', 'updated_at': stamp},
                      {'id': 2, 'city': 'Batumi', 'updated_at': stamp}],
        'products': [dict(id=i, name=n, category=c, updated_at=stamp) for i, n, c in
                     [(1, 'Keyboard', 'Electronics'), (2, 'Mouse', 'Electronics'),
                      (3, 'Notebook', 'Stationery')]],
        'sales': [],
    }
    for line_id, order_id, customer, product, qty, price, discount in [
        (1, 1, 1, 1, 2, '100.00', '20.00'),
        (2, 1, 1, 2, 1, '50.00', '0.00'),
        (3, 2, 2, 3, 3, '10.00', '0.00'),
    ]:
        day1['sales'].append(dict(id=line_id, order_id=order_id, customer_id=customer,
                                 product_id=product, quantity=qty, unit_price=price,
                                 discount=discount, date='2026-01-01', updated_at=stamp))
    rng = random.Random(seed)
    for i in range(extra_orders):
        product = rng.randint(1, 3)
        day1['sales'].append(dict(id=i+4, order_id=i+3, customer_id=rng.randint(1, 2),
                                 product_id=product, quantity=rng.randint(1, 5),
                                 unit_price={1:'100.00', 2:'50.00', 3:'10.00'}[product],
                                 discount='0.00', date='2026-01-01', updated_at=stamp))
    day2 = {'returns': [dict(id=1, line_id=1, date='2026-01-02', quantity=1,
                             updated_at='2026-01-02T12:00:00Z')]}
    correction = {**day1['sales'][1], 'unit_price': '70.00',
                  'updated_at': '2026-01-03T12:00:00Z'}
    for name, content in [('day1.json', day1), ('day2.json', day2),
                          ('day3-correction.json', {'sales': [correction]})]:
        (output / name).write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
    with (output / 'costs.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['product_id', 'effective_from', 'unit_cost', 'updated_at'])
        for product, cost in [(1, '60.00'), (2, '20.00'), (3, '4.00')]:
            writer.writerow([product, '2025-01-01', cost, stamp])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    gen = commands.add_parser('generate')
    gen.add_argument('--output', type=Path, default=ROOT / 'data/generated')
    gen.add_argument('--extra-orders', type=int, default=0)
    gen.add_argument('--seed', type=int, default=42)
    ingest = commands.add_parser('load')
    ingest.add_argument('--batch', type=Path, required=True)
    ingest.add_argument('--costs', type=Path)
    commands.add_parser('check')
    commands.add_parser('report')
    args = parser.parse_args()
    try:
        if args.command == 'generate':
            generate(args.output, args.extra_orders, args.seed)
            print(f'Synthetic data written to {args.output}')
        elif args.command == 'load':
            print(load(args.batch, args.costs))
        elif args.command == 'check':
            psql((ROOT / 'sql/03_checks.sql').read_text(encoding='utf-8'))
            print('All database quality checks passed')
        else:
            print(psql("SELECT json_build_object('net_revenue', coalesce(sum(net_revenue),0), "
                       "'gross_profit', coalesce(sum(gross_profit),0), 'orders', "
                       "count(DISTINCT order_id)) FROM mart.sales_line;"))
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
