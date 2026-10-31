# Power BI Desktop setup

This folder contains measure sources and setup instructions, not a finished PBIX.

1. Get data > PostgreSQL database. Docker server: 127.0.0.1:55432; database:
   retail; user: retail; password: your RETAIL_DB_PASSWORD. Use Import mode.
   Never commit credentials.
2. Import mart.movements as Movements, dwh.dim_product as Products,
   dwh.dim_customer as Customers, dwh.dim_date as Dates and mart.freshness
   as Freshness.
3. Create single-direction 1:* relationships from dimensions to Movements:
   Products.product_id to product_id, Customers.customer_id to customer_id,
   Dates.date_id to event_date. Mark Dates as the date table. Leave Freshness
   disconnected; display its last_successful_load in a separate card.
4. Add each measure in Measures.dax separately. Format money as GEL and ratios
   as percentages.
5. Overview page: Net Revenue, Gross Profit, Orders and Average Order Value cards;
   Net Revenue trend by Dates.date_id; Gross Profit by Products.category;
   a product table with sales, refunds and profit. Add date, city and category
   slicers and the freshness card.
6. Refresh after day 2: all-period Net Revenue = 170, Gross Profit = 78.
   January 2 Net Revenue = -90. After day 3: all-period totals are 190 and 98.

Refunds affect finances on the return date. Average Order Value is gross sales
revenue divided by orders with sales in the current filter context. Refunds do
not enter its numerator. Order counts are not additive across categories because
one order may include several categories.

Period Return Unit Ratio compares flows in the selected period and can exceed
100% when returns relate to earlier sales. A cohort report should instead use
mart.sales_line filtered by sale_date. Never join individual returns directly to
sales in Power Query: multiple returns would multiply sales rows.
