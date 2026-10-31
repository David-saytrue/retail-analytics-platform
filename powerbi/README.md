# Подключение Power BI Desktop

Это исходники мер и инструкция; готового `.pbix` пока нет.

1. Get data → PostgreSQL database. Для Docker: server `127.0.0.1:55432`,
   database `retail`. Пользователь `retail`, пароль — заданный тобой
   `RETAIL_DB_PASSWORD`. Используй Import. Не сохраняй пароль в Git.
2. Загрузи `mart.movements` как **Movements**, а `dwh.dim_product`,
   `dwh.dim_customer`, `dwh.dim_date` как **Products**, **Customers**, **Dates**.
   Дополнительно загрузи `mart.freshness` как **Freshness**.
3. Связи 1:* с одиночной фильтрацией от справочников к Movements:
   Products.product_id → product_id, Customers.customer_id → customer_id,
   Dates.date_id → event_date. Отметь Dates как таблицу дат.
   Freshness остаётся без связей; её дата — отдельная карточка свежести.
4. Добавь меры из `Measures.dax` по одной. Денежным мерам задай GEL,
   Gross Margin и Period Return Unit Ratio — проценты.
5. Страница Overview: карточки Net Revenue, Gross Profit, Orders, Average
   Order Value; линия Net Revenue по Dates.date_id; столбцы Gross Profit
   по Products.category; таблица товаров с выручкой, возвратами и прибылью.
   Срезы: дата, город, категория. Карточка Freshness.last_successful_load.
6. После загрузки второго дня обнови данные: для минимального демо
   Net Revenue за весь период = 170, Gross Profit = 78; за 2 января
   Net Revenue = -90. После исправления третьего дня: 190 и 98 за весь период.

Возврат уменьшает финансовый результат в день возврата. AOV считается как
выручка продаж / число заказов с продажами в выбранном контексте; возвраты
не входят в числитель. Число заказов нельзя суммировать между категориями:
один заказ может содержать товары из нескольких категорий.

В узком периоде доля возвращённых единиц может быть >100%: возвраты могут
относиться к продажам прошлого периода. Для отдельной когортной страницы
используй mart.sales_line с фильтром по sale_date и вернувшиеся единицы
по исходной продаже. Не соединяй сырые возвраты с продажами в Power Query:
это размножит строки при нескольких возвратах на одну позицию.
