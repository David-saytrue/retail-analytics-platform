"""Daily immutable-inbox ingestion, with transactional publication per package."""
from datetime import timedelta
from pathlib import Path
import os

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id='retail_daily_ingestion',
    schedule='0 6 * * *',
    start_date=pendulum.datetime(2026, 1, 1, tz='Asia/Tbilisi'),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(minutes=20),
    default_args={'owner': 'retail', 'retries': 2, 'retry_delay': timedelta(minutes=1),
                  'execution_timeout': timedelta(minutes=5)},
    tags=['retail', 'postgresql', 'portfolio'],
    doc_md='''
    Runs daily at 06:00 Asia/Tbilisi. Publishes READY.json packages in directory-name
    order, then validates the warehouse and writes data/reports/latest.json.
    Empty inboxes are successful no-ops. Ready packages are immutable and retained;
    reruns replay source versions safely. Atomicity is per package, not per Dag run.
    Source corrections use updated_at, never arrival order. No scheduled demo generation.
    ''',
)
def retail_daily_ingestion():
    @task.short_circuit()
    def has_ready_input():
        from pipeline import ready_batches
        return bool(ready_batches(Path(os.environ['RETAIL_INBOX'])))

    @task()
    def publish_ready_batches():
        from pipeline import publish_batches, ready_batches
        inbox = Path(os.environ['RETAIL_INBOX'])
        return publish_batches(inbox, ready_batches(inbox))

    @task()
    def validate_financial_marts():
        from pipeline import validate_and_report
        return validate_and_report(Path(os.environ['RETAIL_REPORTS']))

    has_ready_input() >> publish_ready_batches() >> validate_financial_marts()


retail_daily_ingestion()
