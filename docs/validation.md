# First-version validation: October 31, 2026

Environment: Windows, Python 3.10.9, PostgreSQL 17. Checks used an isolated
local cluster on loopback port 55439, without touching existing learning databases.
The temporary server was stopped afterward.

## Completed checks

- python -m unittest discover -s tests -v: 3 tests passed.
- python tests/integration.py: one end-to-end scenario with seven rollback
  cases passed on the final implementation.
- python -m compileall -q retail.py tests: passed.
- docker compose config --quiet: passed with a temporary password variable.
- git diff --check: passed for tracked changes.

Integration coverage: initial ingestion, reruns, returns, price corrections,
old batches, future costs, multiple returns, excess return quantities, missing
references, returns before sales, conflicting versions, missing historical costs,
inconsistent customer within an order, recovery after failure and allocating
one cent across three partial returns.

## Larger smoke run

Seed 42; extra_orders=10000. Sales lines: 10,003; distinct orders: 10,002.
Initial ingestion accepted 10,011 raw versions in approximately 1.285 seconds.
A repeat accepted zero new versions in approximately 0.925 seconds.
Return and correction batches each accepted one new version. Final net revenue:
1,583,910.00 GEL; gross profit: 751,530.00 GEL.

Timings are single local measurements around Python load(), including client
startup, schema preparation, auditing, model refresh and SQL checks. They are
smoke-test observations, not a load benchmark or an SLA.

## Remaining verification limits

- Power BI direct PostgreSQL connector refresh remains unverified; the report
  was subsequently verified with its SQL snapshot (see below).
- Concurrent execution and abrupt process termination: dedicated tests remain
  future work; publication uses an advisory transaction lock.

Documentation was subsequently translated to English; pipeline behavior was unchanged.

## CI publication

The GitHub CLI workflow scope was subsequently granted and the workflow was
prepared for publication. Live results are available in the repository Actions tab.

## Docker and Power BI validation: November 2, 2026

- Docker Engine 28.5.1: PostgreSQL container healthy on 127.0.0.1:55432.
- Existing Dockerfile built and the Compose demo completed successfully.
- Day 1: net revenue 260, gross profit 108 GEL. Day 2: 170 and 78 GEL.
- Repeated day 2 accepted zero versions; database quality checks passed.
- Price correction: 190 and 98 GEL. Older day 1 accepted zero versions and
  preserved the correction; database quality checks passed.
- Three unit tests passed inside the built application image.
- Power BI Desktop 2.159.883.0 loaded the generated PBIP and refreshed six
  tables, including the dedicated Metrics table, from the embedded SQL snapshot.
- DAX visuals: net revenue 190, gross profit 98, orders 2, AOV 140 GEL.
- Selecting Stationery on the category visual: revenue 30, profit 18, orders 1,
  AOV 30 GEL. Clearing the selection restored the all-period results.
- Desktop saved both PBIP and a packaged PBIX containing a DataModel.
- Direct PostgreSQL import requires a local credential entry and remains unverified.

The snapshot is a two-day reconciliation dataset, not a realistic business history.
No Power BI Service publication or automatic PBIX refresh is configured.
Airflow was subsequently implemented and verified as described below.

## Airflow portfolio completion: November 2, 2026

- Pinned image: apache/airflow:3.3.1-python3.12; custom image built successfully.
- DAG parser verified task IDs/dependencies, Asia/Tbilisi timezone, two task retries,
  catchup disabled and one active run/task.
- Public PowerShell Start and Status helpers executed successfully. The metadata
  database and scheduler health checks passed; API health reported metadata,
  scheduler, DAG processor and triggerer healthy.
- Actual scheduler run `scheduled__2026-11-02T02:00:00+00:00`: success, all three tasks.
- Manual run `manual__2026-11-02T17:00:06.235011+00:00`: success, all three tasks.
- Both runs replayed three packages and published zero new raw versions against
  the existing corrected demo; revenue 190.00, gross profit 98.00 GEL, two orders.
- A timestamped successful financial summary was written to data/reports/latest.json.
- Six unit tests passed, including incomplete input, corrupt later input rejected
  before any publication, immutable demo replay and traversal rejection.
- Original end-to-end database scenario passed in a fresh dedicated database.
- Separate inbox integration passed in another fresh database: initial 13 source
  versions, retry 0, financial reconciliation, SQL rejection of excessive returns,
  unchanged totals/report after failure, quarantine and successful recovery.
- Tests never reset an existing database or remove a data volume.

CI now runs unit and both PostgreSQL integration suites, plus an independent build
and parser check using the pinned Airflow image. See the linked live Actions results
in the repository for the publication run's final status.

This completes the local portfolio v1 scope: ingestion, warehouse, financial marts,
quality/recovery checks, Airflow scheduling and a working snapshot Power BI report.
Production operations, direct Power BI connector refresh and Power BI Service
publishing remain outside the verified scope.
