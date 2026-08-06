-- ============================================================================
-- Run this once in a Databricks SQL warehouse / notebook BEFORE deploying the
-- bundle, so that the postgres_synced_tables resource has a source table to
-- sync from. Update the catalog/schema to match your `storage_catalog` /
-- `storage_schema` bundle variables.
-- ============================================================================

CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.sales;

CREATE TABLE IF NOT EXISTS main.sales.orders (
  order_id     BIGINT NOT NULL,
  customer     STRING,
  item         STRING,
  quantity     INT,
  amount       DECIMAL(10, 2),
  status       STRING,
  ordered_at   TIMESTAMP
)
-- Change Data Feed is required for continuous sync into Lakebase.
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO main.sales.orders VALUES
  (1, 'Ava Chen',       'Wireless Mouse',    2,  39.98, 'shipped',   current_timestamp()),
  (2, 'Marcus Diallo',  'Mechanical KB',     1, 129.00, 'shipped',   current_timestamp()),
  (3, 'Priya Nair',     'USB-C Hub',         3,  87.00, 'processing',current_timestamp()),
  (4, 'Liam O''Connor', '27" Monitor',       1, 299.99, 'processing',current_timestamp()),
  (5, 'Sofia Reyes',    'Webcam 1080p',      2,  59.98, 'delivered', current_timestamp());
