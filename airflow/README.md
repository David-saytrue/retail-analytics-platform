# Airflow orchestration

Apache Airflow 3.3.1 / Python 3.12, using the official image. The optional Compose
overlay adds a dedicated metadata PostgreSQL and a local `standalone` service with
LocalExecutor. Standalone starts the API server, scheduler, DAG processor and
triggerer together. This is a local learning deployment, not production HA.
The application database and the metadata database use separate users and volumes.
No Docker socket or privileged mode is used.

## Windows quick start

Docker Desktop must be running. Run from the repository in PowerShell 7:

```powershell
./scripts/retail.ps1 -Action Start
./scripts/retail.ps1 -Action PrepareDemo
./scripts/retail.ps1 -Action Trigger
./scripts/retail.ps1 -Action Status
./scripts/retail.ps1 -Action CopyAirflowPassword
```

Open http://localhost:8086; username `admin`. Paste the password copied by the last
command. Stop only this project with `./scripts/retail.ps1 -Action Stop`.
Never remove volumes to fix credentials. On Windows the helper stores generated
database passwords under ignored `artifacts/local-credentials.clixml`, protected
by the current Windows user's DPAPI. Preserve that file locally alongside the
database volumes; it is not portable to another user or computer.

For another OS, export `RETAIL_DB_PASSWORD` and a URL-safe `AIRFLOW_DB_PASSWORD`,
then use `docker compose -f compose.yaml -f compose.airflow.yaml --profile airflow`.
Keep both passwords for the lifetime of their database volumes. On Linux, make
`data/reports` writable by the container user (UID 50000), and the inbox readable.
Build `app` and
`airflow`, then `up -d --wait airflow`. Run `app` with entrypoint `python` and
arguments `pipeline.py prepare-demo` to prepare the sample inbox. The UI uses
SimpleAuthManager for local development; do not expose port 8086 externally.

## DAG behavior

`retail_daily_ingestion` runs daily at **06:00 Asia/Tbilisi (02:00 UTC)** after
unpausing. `catchup=False`; one active run and one active task. Each task has two
retries, a one-minute retry delay and a five-minute timeout; run timeout is 20 minutes.
PrepareDemo only stages deterministic input; it does not start a Dag run or regenerate
data on a schedule. Trigger unpauses scheduling and requests an additional manual run.

Tasks: `has_ready_input`, `publish_ready_batches`, `validate_financial_marts`.
An empty inbox is a successful no-op and downstream tasks are skipped. Otherwise:

1. Discover ready directories in lexical order. Prefix dependent packages with
   ordered names such as `01-sales`, `02-return`, `03-correction`.
2. Verify SHA-256 checksums and validate all ready packages before database writes.
3. Publish packages sequentially using the existing raw/model/check transaction.
4. Run quality checks again and atomically write `data/reports/latest.json`.

The Airflow task and run status show failures; `ops.runs` records database attempts.
Malformed input rejected before connecting has no database audit row. Retrying a task
replays all retained packages safely, including ones already committed. The raw
version key deduplicates exact retries, rejects conflicts, and preserves corrections
when old packages are replayed. No global watermark drops late updates.

Atomicity is **per package**, not across the whole Dag run: if a later package fails
a SQL business rule, earlier successful packages remain published and no new report
file is written. A previous `latest.json` remains a timestamped historical result;
it must not be interpreted as the current failed run's success. Airflow run state and
`ops.runs` are the failure signals. No external alert delivery is configured.

## Input contract

Each directory under `data/inbox/` contains `batch.json`, optional `costs.csv`, and
`READY.json` with exactly `batch_sha256` and `costs_sha256` (null when no costs file).
Names allow ASCII letters, digits, underscores, hyphens and dots, starting with an
alphanumeric character. Dot-prefixed staging directories are ignored. Symlinked
packages/files are not accepted. Publish READY.json **last**, after closing both
data files. After publication, packages are immutable: use a new package name and
a later source `updated_at` to correct a record. Never rewrite an accepted package.

Retained packages are intentionally replayed on each run; database ingestion is
idempotent, but this is a small-demo strategy rather than an optimized file catalog.
Missing source records do not mean deletion. No automatic archiving or deletion occurs.

## Verification

```powershell
python -m unittest discover -s tests -v
# Inside the Airflow service:
docker compose -f compose.yaml -f compose.airflow.yaml --profile airflow exec airflow python /opt/retail/airflow/verify_dag.py
```

The workflow tests input corruption, incomplete packages and traversal, real database
replay/reconciliation in a fresh database, and DAG parsing in the pinned runtime.
After demo ingestion: net revenue 190 GEL, gross profit 98 GEL, two orders.
Another trigger must publish zero new raw versions and leave these totals unchanged.
The report file is an operational SQL summary; it does not refresh a Power BI PBIX.
Refresh Power BI separately. Its embedded demo snapshot only changes when explicitly
replaced; set `UsePostgreSQL=true` for database imports and configure local credentials.

References: [TaskFlow](https://airflow.apache.org/docs/apache-airflow/3.3.1/tutorial/taskflow.html),
[Docker deployment](https://airflow.apache.org/docs/apache-airflow/3.3.1/howto/docker-compose/index.html),
[SimpleAuthManager](https://airflow.apache.org/docs/apache-airflow/3.3.1/core-concepts/auth-manager/simple/index.html).
