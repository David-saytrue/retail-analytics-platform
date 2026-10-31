# Retail analytics platform

- Synthetic data only. Do not use personal data or credentials from other projects.
- Python 3.10+, standard library, PostgreSQL 17+. `psql` is the database client.
- Run `python -m unittest discover -s tests -v` for unit tests.
- Integration tests require a dedicated disposable database and `RETAIL_TEST_DB=1`:
  `python tests/integration.py`. They reject a nonempty application schema.
- Preserve raw source versions. Load, model refresh, quality checks and success status
  must commit together; failure must leave the previous published model intact.
- Money: Decimal in Python, NUMERIC in SQL; currency GEL, no tax/shipping in v1.
- Grain: one sales line / one return event. Aggregate returns before joining sales.
- No commit, push, database reset or volume removal without a user request.
