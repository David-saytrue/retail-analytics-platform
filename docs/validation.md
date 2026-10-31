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

## Not verified

- Docker image build/runtime: Docker Desktop engine was not running.
- Power BI Desktop: no PBIX has been built; measures have not been evaluated by
  the DAX engine.
- Concurrent execution and abrupt process termination: dedicated tests remain
  future work; publication uses an advisory transaction lock.

Documentation was subsequently translated to English; pipeline behavior was unchanged.

## CI publication

The GitHub CLI workflow scope was subsequently granted and the workflow was
prepared for publication. Live results are available in the repository Actions tab.
