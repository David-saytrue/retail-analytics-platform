CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS ops.runs (
    run_id uuid PRIMARY KEY,
    source_file text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    new_versions integer,
    error text
);
CREATE TABLE IF NOT EXISTS raw.events (
    entity text NOT NULL CHECK (entity IN ('customers','products','sales','returns','costs')),
    record_id text NOT NULL,
    updated_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    first_run_id uuid NOT NULL REFERENCES ops.runs,
    loaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (entity, record_id, updated_at)
);
CREATE OR REPLACE VIEW staging.latest AS
SELECT DISTINCT ON (entity, record_id)
    entity, record_id, updated_at, payload
FROM raw.events
ORDER BY entity, record_id, updated_at DESC;

CREATE TABLE IF NOT EXISTS dwh.dim_customer (
    customer_id integer PRIMARY KEY,
    city text NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.dim_product (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    category text NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.dim_date (
    date_id date PRIMARY KEY,
    year integer NOT NULL,
    month integer NOT NULL,
    month_start date NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.product_cost (
    product_id integer NOT NULL REFERENCES dwh.dim_product,
    effective_from date NOT NULL,
    unit_cost numeric(14,2) NOT NULL CHECK (unit_cost >= 0),
    PRIMARY KEY (product_id, effective_from)
);
CREATE TABLE IF NOT EXISTS dwh.fact_sales (
    line_id integer PRIMARY KEY,
    order_id integer NOT NULL,
    customer_id integer NOT NULL REFERENCES dwh.dim_customer,
    product_id integer NOT NULL REFERENCES dwh.dim_product,
    sale_date date NOT NULL REFERENCES dwh.dim_date,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(14,2) NOT NULL CHECK (unit_price >= 0),
    discount numeric(14,2) NOT NULL CHECK (discount >= 0),
    unit_cost numeric(14,2) NOT NULL CHECK (unit_cost >= 0),
    revenue numeric(16,2) NOT NULL CHECK (revenue >= 0),
    cogs numeric(16,2) NOT NULL CHECK (cogs >= 0),
    CHECK (discount <= quantity * unit_price)
);
CREATE TABLE IF NOT EXISTS dwh.fact_returns (
    return_id integer PRIMARY KEY,
    line_id integer NOT NULL REFERENCES dwh.fact_sales,
    return_date date NOT NULL REFERENCES dwh.dim_date,
    quantity integer NOT NULL CHECK (quantity > 0),
    refund numeric(16,2) NOT NULL CHECK (refund >= 0),
    recovered_cogs numeric(16,2) NOT NULL CHECK (recovered_cogs >= 0)
);
