# Lesson 1: Why the report is trustworthy

A shop sells two keyboards at 100 GEL each with a 20 GEL line discount.
Revenue is 2 * 100 - 20 = 180. Each keyboard costs 60, so line profit is 60.
The next day one keyboard is returned: refund 90, recovered inventory cost 60.
Profit decreases by 30, not 90, because the returned item goes back into stock.

## Raw versions and current state

Raw is the journal of accepted source versions. A price correction from 50 to 70
keeps both versions and the run that accepted each. staging.latest selects the
current version using DISTINCT ON and updated_at DESC.

```sql
SELECT record_id, updated_at, payload, first_run_id
FROM raw.events WHERE entity = 'sales' AND record_id = '2'
ORDER BY updated_at;
```

## Grain: what one row represents

An order can contain several products. The demo has three sales lines but two
orders. Average order value is 260 / 2 = 130, not 260 / 3.

```sql
SELECT count(*) AS lines, count(DISTINCT order_id) AS orders
FROM dwh.fact_sales;
```

## How a join can double revenue

A sales line has revenue 180. Joining two return events directly produces two
rows containing 180 each; SUM incorrectly reports 360. mart.sales_line first
aggregates returns to one row per line_id and then joins them to sales.

## Safe reruns and late data

A source may resend a batch after a network failure. The raw primary key and
ON CONFLICT DO NOTHING skip existing versions. Warehouse rows update by business
key. Compare raw counts and report totals before and after repeating day 2.

updated_at is the source change time; loaded_at is our ingestion time. An old
batch can arrive after a correction, so arrival order must not decide freshness.

## Transactions and recovery

If a return references a nonexistent sale, publishing half a batch would make
the report inconsistent. The transaction rolls back the entire batch's raw and
model changes, preserving the previous report. A separate audit update records
the failure.

## Interview exercises

1. Why does one keyboard return reduce profit by 30 rather than 90?
2. What happens when day2.json is loaded twice?
3. Why cannot an old day1.json overwrite the day 3 correction?
4. Why is missing cost an error instead of a zero expense?
5. How do sale-date cohort reporting and financial movement-date reporting differ?

Find the corresponding SQL formula or constraint and reproduce each scenario.
