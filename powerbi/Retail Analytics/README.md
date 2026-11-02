# Retail Analytics — Power BI Project

Open `Retail Analytics.pbip` in Power BI Desktop, then select Refresh.
The default source is the verified SQL demo snapshot embedded in the model, not a live database connection.
All data is synthetic. No passwords are stored in this project.

## Direct PostgreSQL refresh

Transform data > Edit parameters: set `UsePostgreSQL` to true, apply and refresh.
Database server: `127.0.0.1:55432`; database: `retail`; user: `retail`.
Enter the local demo password in Power BI's database credential dialog.
Credentials belong in Desktop's local credential store, never in project files.
Refresh all five tables together after each successful pipeline run.

## Model and expected values

Movements has one row per sale or return event. Products, Customers and Dates filter
Movements through single-direction one-to-many relationships. Freshness is disconnected.
Date filters recognize refunds on their event date. No sales/returns join multiplies rows.

All-period totals: gross sales 280 GEL; refunds 90 GEL; net revenue 190 GEL;
net COGS 92 GEL; gross profit 98 GEL; orders 2; AOV 140 GEL.
January 2: net revenue -90 GEL and gross profit -30 GEL; orders and AOV are blank.
Electronics: net revenue 160 GEL; profit 80 GEL. Stationery: revenue 30 GEL; profit 18 GEL.
Order counts are not additive across categories. Period Return Unit Ratio compares
period flows, not a sale cohort. An empty denominator produces a blank through DIVIDE.

The small two-day dataset is for reconciliation and learning, not business conclusions.
Save As PBIX in Desktop if a packaged copy is needed; do not publish credentials or local cache files.
