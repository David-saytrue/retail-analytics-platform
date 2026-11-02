"""Executed in the pinned Airflow image; does not connect to the retail database."""
from airflow.models import DagBag

bag = DagBag(dag_folder='/opt/airflow/dags')
if bag.import_errors:
    raise RuntimeError(bag.import_errors)
dag = bag.dags['retail_daily_ingestion']
assert set(dag.task_ids) == {'has_ready_input', 'publish_ready_batches', 'validate_financial_marts'}
assert str(dag.timezone) == 'Asia/Tbilisi'
assert dag.max_active_runs == 1 and dag.max_active_tasks == 1
assert not dag.catchup
assert dag.get_task('publish_ready_batches').retries == 2
assert dag.get_task('publish_ready_batches').downstream_task_ids == {'validate_financial_marts'}
print('Airflow DAG import, timezone, concurrency, retries and dependencies verified')
