-- Query 1: Unbalanced entries
SELECT posting_id,
       ROUND(SUM(CASE WHEN cd_flag = 'D' THEN amount ELSE -amount END), 2) AS diff
FROM ledger
GROUP BY posting_id
HAVING ABS(SUM(CASE WHEN cd_flag = 'D' THEN amount ELSE -amount END)) > 0.01;

-- Query 2: Entries per month
SELECT LEFT(CONVERT(varchar(10), posting_date, 120), 7) AS [month],
       COUNT(DISTINCT posting_id) AS entries
FROM ledger
GROUP BY LEFT(CONVERT(varchar(10), posting_date, 120), 7)
ORDER BY [month];

-- Query 3: Flagged entries per user (JOIN)
WITH e AS (
    SELECT posting_id, MIN([user]) AS [user]
    FROM ledger
    GROUP BY posting_id
)
SELECT e.[user],
       COUNT(*) AS entries,
       SUM(CASE WHEN r.posting_id IS NOT NULL THEN 1 ELSE 0 END) AS flagged
FROM e
LEFT JOIN review_list r ON r.posting_id = e.posting_id
GROUP BY e.[user]
ORDER BY flagged DESC;

-- Query 4: Precision by priority (GROUP BY / CAST)
SELECT priority,
       COUNT(*) AS entries,
       SUM(CAST(actual_label AS int)) AS anomalies,
       ROUND(1.0 * SUM(CAST(actual_label AS int)) / COUNT(*), 3) AS precision_rate
FROM review_list
GROUP BY priority
ORDER BY precision_rate DESC;

-- Query 5: Top 10 entries to review (TOP / ORDER BY)
SELECT TOP 10 posting_id, [user], max_amount, rules_hit, priority
FROM review_list
ORDER BY rules_hit DESC, max_amount DESC;