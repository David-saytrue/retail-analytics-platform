-- Raising an exception aborts the publishing transaction.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM dwh.fact_sales GROUP BY order_id
        HAVING count(DISTINCT customer_id) > 1 OR count(DISTINCT sale_date) > 1
    ) THEN RAISE EXCEPTION 'DQ: inconsistent customer or date within an order'; END IF;
    IF EXISTS (
        SELECT 1 FROM dwh.fact_returns r JOIN dwh.fact_sales s USING (line_id)
        WHERE r.return_date < s.sale_date
    ) THEN RAISE EXCEPTION 'DQ: return predates sale'; END IF;
    IF EXISTS (
        SELECT 1 FROM mart.sales_line
        WHERE returned_quantity > quantity OR refund > revenue
    ) THEN RAISE EXCEPTION 'DQ: returns exceed sold quantity or value'; END IF;
    IF (SELECT count(*) FROM dwh.fact_sales) <>
       (SELECT count(*) FROM staging.latest WHERE entity = 'sales')
    THEN RAISE EXCEPTION 'DQ: sales row reconciliation failed'; END IF;
    IF (SELECT count(*) FROM dwh.fact_returns) <>
       (SELECT count(*) FROM staging.latest WHERE entity = 'returns')
    THEN RAISE EXCEPTION 'DQ: returns row reconciliation failed'; END IF;
    IF coalesce((SELECT sum(revenue) FROM dwh.fact_sales), 0) <>
       coalesce((SELECT sum((payload->>'quantity')::int *
                       (payload->>'unit_price')::numeric - (payload->>'discount')::numeric)
                 FROM staging.latest WHERE entity = 'sales'), 0)
    THEN RAISE EXCEPTION 'DQ: source revenue reconciliation failed'; END IF;
    IF coalesce((SELECT sum(net_revenue) FROM mart.sales_line), 0) <>
       coalesce((SELECT sum(net_revenue) FROM mart.daily_finance), 0)
    THEN RAISE EXCEPTION 'DQ: movement revenue reconciliation failed'; END IF;
    IF coalesce((SELECT sum(gross_profit) FROM mart.sales_line), 0) <>
       coalesce((SELECT sum(gross_profit) FROM mart.daily_finance), 0)
    THEN RAISE EXCEPTION 'DQ: movement profit reconciliation failed'; END IF;
END $$;
