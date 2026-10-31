INSERT INTO dwh.dim_customer
SELECT (payload->>'id')::int, payload->>'city'
FROM staging.latest WHERE entity = 'customers'
ON CONFLICT (customer_id) DO UPDATE SET city = excluded.city;

INSERT INTO dwh.dim_product
SELECT (payload->>'id')::int, payload->>'name', payload->>'category'
FROM staging.latest WHERE entity = 'products'
ON CONFLICT (product_id) DO UPDATE
SET product_name = excluded.product_name, category = excluded.category;

INSERT INTO dwh.product_cost
SELECT (payload->>'product_id')::int, (payload->>'effective_from')::date,
       (payload->>'unit_cost')::numeric
FROM staging.latest WHERE entity = 'costs'
ON CONFLICT (product_id, effective_from) DO UPDATE SET unit_cost = excluded.unit_cost;

-- A complete date dimension between the first and last business event.
INSERT INTO dwh.dim_date
SELECT d::date, extract(year FROM d)::int, extract(month FROM d)::int,
       date_trunc('month', d)::date
FROM generate_series(
    (SELECT min((payload->>'date')::date) FROM staging.latest WHERE entity IN ('sales','returns')),
    (SELECT max((payload->>'date')::date) FROM staging.latest WHERE entity IN ('sales','returns')),
    interval '1 day') AS dates(d)
ON CONFLICT DO NOTHING;

INSERT INTO dwh.fact_sales
SELECT (p->>'id')::int, (p->>'order_id')::int, (p->>'customer_id')::int,
       (p->>'product_id')::int, (p->>'date')::date,
       (p->>'quantity')::int, (p->>'unit_price')::numeric,
       (p->>'discount')::numeric, cost.unit_cost,
       (p->>'quantity')::int * (p->>'unit_price')::numeric - (p->>'discount')::numeric,
       (p->>'quantity')::int * cost.unit_cost
FROM (SELECT payload AS p FROM staging.latest WHERE entity = 'sales') s
LEFT JOIN LATERAL (
    SELECT unit_cost FROM dwh.product_cost
    WHERE product_id = (p->>'product_id')::int
      AND effective_from <= (p->>'date')::date
    ORDER BY effective_from DESC LIMIT 1
) cost ON true
ON CONFLICT (line_id) DO UPDATE SET
    order_id = excluded.order_id, customer_id = excluded.customer_id,
    product_id = excluded.product_id, sale_date = excluded.sale_date,
    quantity = excluded.quantity, unit_price = excluded.unit_price,
    discount = excluded.discount, unit_cost = excluded.unit_cost,
    revenue = excluded.revenue, cogs = excluded.cogs;

-- Refund at the original discounted price. COGS reversal uses sale-time cost.
INSERT INTO dwh.fact_returns
-- Cumulative allocation preserves cents when a line is returned in parts.
WITH return_events AS (
    SELECT payload AS p, (payload->>'quantity')::int AS qty,
           sum((payload->>'quantity')::int) OVER (
               PARTITION BY payload->>'line_id'
               ORDER BY (payload->>'date')::date, (payload->>'id')::int
           ) AS cumulative_qty
    FROM staging.latest WHERE entity = 'returns'
)
SELECT (p->>'id')::int, s.line_id, (p->>'date')::date, (p->>'quantity')::int,
       round(s.revenue * cumulative_qty / s.quantity, 2)
           - round(s.revenue * (cumulative_qty - qty) / s.quantity, 2),
       s.unit_cost * (p->>'quantity')::int
FROM return_events r
LEFT JOIN dwh.fact_sales s ON s.line_id = (p->>'line_id')::int
ON CONFLICT (return_id) DO UPDATE SET
    line_id = excluded.line_id, return_date = excluded.return_date,
    quantity = excluded.quantity, refund = excluded.refund,
    recovered_cogs = excluded.recovered_cogs;

-- A sales line stays one row even when it has several return events.
CREATE OR REPLACE VIEW mart.sales_line AS
WITH returns AS (
    SELECT line_id, sum(quantity) AS returned_quantity,
           sum(refund) AS refund, sum(recovered_cogs) AS recovered_cogs
    FROM dwh.fact_returns GROUP BY line_id
)
SELECT s.*, coalesce(r.returned_quantity, 0) AS returned_quantity,
       coalesce(r.refund, 0) AS refund,
       s.revenue - coalesce(r.refund, 0) AS net_revenue,
       s.cogs - coalesce(r.recovered_cogs, 0) AS net_cogs,
       s.revenue - coalesce(r.refund, 0) - s.cogs
           + coalesce(r.recovered_cogs, 0) AS gross_profit
FROM dwh.fact_sales s LEFT JOIN returns r USING (line_id);

-- Financial movements: revenue on sale date, refund on return date.
CREATE OR REPLACE VIEW mart.movements AS
SELECT 'sale:' || line_id AS movement_id, sale_date AS event_date,
       order_id, customer_id, product_id, quantity AS sold_units,
       0::int AS returned_units, revenue, 0::numeric AS refunds, cogs
FROM dwh.fact_sales
UNION ALL
SELECT 'return:' || r.return_id, r.return_date,
       s.order_id, s.customer_id, s.product_id, 0, r.quantity,
       0::numeric, r.refund, -r.recovered_cogs
FROM dwh.fact_returns r JOIN dwh.fact_sales s USING (line_id);

CREATE OR REPLACE VIEW mart.daily_finance AS
SELECT event_date, sum(revenue) AS sales_revenue, sum(refunds) AS refunds,
       sum(revenue - refunds) AS net_revenue, sum(cogs) AS net_cogs,
       sum(revenue - refunds - cogs) AS gross_profit,
       sum(sold_units) AS sold_units, sum(returned_units) AS returned_units
FROM mart.movements GROUP BY event_date;

CREATE OR REPLACE VIEW mart.freshness AS
SELECT max(finished_at) FILTER (WHERE status = 'success') AS last_successful_load,
       (SELECT max(updated_at) FROM raw.events) AS latest_source_update,
       count(*) FILTER (WHERE status = 'failed') AS failed_runs
FROM ops.runs;
