-- ProcureIQ SQL analysis starter queries.
-- Import the cleaned output as a table named transactions.
-- Expected columns: amount, supplier, category, date, item, department, po_number, invoice_id.

-- 1. Total spend and average transaction
SELECT SUM(amount) AS total_spend,
       COUNT(*) AS transaction_count,
       AVG(amount) AS average_transaction
FROM transactions;

-- 2. Spend by supplier and supplier share
SELECT supplier,
       SUM(amount) AS total_spend,
       COUNT(*) AS transaction_count,
       100.0 * SUM(amount) / NULLIF((SELECT SUM(amount) FROM transactions), 0) AS spend_share_pct
FROM transactions
WHERE supplier IS NOT NULL
GROUP BY supplier
ORDER BY total_spend DESC;

-- 3. Spend by category
SELECT category, SUM(amount) AS total_spend, COUNT(*) AS transaction_count
FROM transactions
WHERE category IS NOT NULL
GROUP BY category
ORDER BY total_spend DESC;

-- 4. Monthly spend (DuckDB syntax)
SELECT DATE_TRUNC('month', CAST(date AS DATE)) AS spend_month,
       SUM(amount) AS total_spend
FROM transactions
WHERE date IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- 5. Repeated invoice IDs for review (not confirmed duplicate payments)
SELECT LOWER(TRIM(invoice_id)) AS invoice_key,
       COUNT(*) AS row_count,
       COUNT(DISTINCT supplier) AS supplier_count,
       COUNT(DISTINCT amount) AS amount_count
FROM transactions
WHERE invoice_id IS NOT NULL AND TRIM(invoice_id) <> ''
GROUP BY LOWER(TRIM(invoice_id))
HAVING COUNT(*) > 1
ORDER BY row_count DESC;

-- 6. Supplier concentration inputs
WITH supplier_spend AS (
    SELECT supplier, SUM(amount) AS total_spend
    FROM transactions
    WHERE supplier IS NOT NULL
    GROUP BY supplier
), shares AS (
    SELECT supplier, total_spend,
           total_spend / NULLIF((SELECT SUM(total_spend) FROM supplier_spend), 0) AS share
    FROM supplier_spend
)
SELECT SUM(share * share) * 10000 AS supplier_hhi
FROM shares;
