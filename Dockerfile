FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY retail.py ./
COPY sql ./sql
COPY tests ./tests
ENTRYPOINT ["python", "retail.py"]
