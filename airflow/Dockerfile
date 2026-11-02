FROM apache/airflow:3.3.1-python3.12
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/airflow/state && chown airflow:root /opt/airflow/state
COPY --chown=airflow:root retail.py pipeline.py /opt/retail/
COPY --chown=airflow:root sql /opt/retail/sql
COPY --chown=airflow:root airflow/dags /opt/airflow/dags
USER airflow
ENV PYTHONPATH=/opt/retail
COPY --chown=airflow:root airflow/verify_dag.py /opt/retail/airflow/verify_dag.py
