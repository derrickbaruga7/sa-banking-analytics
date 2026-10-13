-- All findings use [2026-08-01, 2026-09-26): two equal 28-day windows.
-- The September 27 ingestion exercise is outside the investigation window.

-- name: quality
SELECT COALESCE(rejection_reason, 'accepted') AS disposition, COUNT(*) AS attempts
FROM stg_attempt_validation GROUP BY rejection_reason;

-- name: periods
SELECT CASE WHEN attempt_date < '2026-08-29' THEN 'Before release' ELSE 'After release' END AS period,
 COUNT(*) AS attempts, SUM(submitted_at IS NOT NULL) AS submitted,
 SUM(outcome='succeeded') AS succeeded, SUM(outcome='failed') AS failed,
 SUM(outcome='unresolved') AS unresolved,
 COUNT(DISTINCT CASE WHEN outcome='failed' THEN customer_id END) AS affected_customers,
 SUM(support_case_count) AS support_cases, SUM(support_case_count>0) AS supported_attempts,
 ROUND(100.0*SUM(outcome='succeeded')/COUNT(*),2) AS completion_pct,
 ROUND(100.0*SUM(submitted_at IS NOT NULL)/COUNT(*),2) AS submission_pct,
 ROUND(100.0*SUM(outcome='failed')/NULLIF(SUM(submitted_at IS NOT NULL),0),2) AS failure_pct
FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-01' AND attempt_date < '2026-09-26'
GROUP BY period ORDER BY MIN(attempt_date);

-- name: version_os
SELECT app_version, device_os, COUNT(*) AS attempts,
 SUM(submitted_at IS NOT NULL) AS submitted, SUM(outcome='succeeded') AS succeeded,
 SUM(outcome='failed') AS failed,
 COUNT(DISTINCT CASE WHEN outcome='failed' THEN customer_id END) AS affected_customers,
 SUM(support_case_count) AS support_cases, SUM(support_case_count>0) AS supported_attempts,
 ROUND(100.0*SUM(outcome='succeeded')/COUNT(*),2) AS completion_pct,
 ROUND(100.0*SUM(outcome='failed')/NULLIF(SUM(submitted_at IS NOT NULL),0),2) AS failure_pct,
 ROUND(100.0*SUM(support_case_count>0)/COUNT(*),2) AS support_contact_pct
FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26'
GROUP BY app_version, device_os ORDER BY failure_pct DESC;

-- name: segments
SELECT app_version, device_os, segment, COUNT(*) AS attempts,
 SUM(submitted_at IS NOT NULL) AS submitted, SUM(outcome='failed') AS failed,
 ROUND(100.0*SUM(outcome='failed')/NULLIF(SUM(submitted_at IS NOT NULL),0),2) AS failure_pct
FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26'
GROUP BY app_version, device_os, segment ORDER BY app_version, device_os, segment;

-- name: provinces
SELECT province, COUNT(*) AS attempts, SUM(submitted_at IS NOT NULL) AS submitted,
 SUM(outcome='failed') AS failed,
 COUNT(DISTINCT CASE WHEN outcome='failed' THEN customer_id END) AS affected_customers,
 ROUND(100.0*SUM(outcome='failed')/NULLIF(SUM(submitted_at IS NOT NULL),0),2) AS failure_pct
FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26'
GROUP BY province ORDER BY failure_pct DESC;

-- name: repeated_failures
SELECT customer_id, COUNT(*) AS attempts, SUM(outcome='failed') AS failed,
 ROUND(100.0*SUM(outcome='failed')/NULLIF(SUM(submitted_at IS NOT NULL),0),2) AS failure_pct
FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-01' AND attempt_date < '2026-09-26'
GROUP BY customer_id HAVING SUM(outcome='failed') >= 3
ORDER BY failed DESC, customer_id;

-- name: reasons
WITH denominators AS (
 SELECT app_version, device_os, SUM(submitted_at IS NOT NULL) AS submitted
 FROM fact_payment_attempt
 WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26'
 GROUP BY app_version, device_os
)
SELECT f.app_version, f.device_os, failure_reason, COUNT(*) AS failures, d.submitted,
 ROUND(100.0*COUNT(*)/NULLIF(d.submitted,0),2) AS submitted_reason_pct
FROM fact_payment_attempt f JOIN denominators d USING(app_version,device_os)
WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26' AND outcome='failed'
GROUP BY f.app_version,f.device_os,f.failure_reason,d.submitted ORDER BY failures DESC;

-- name: median_duration
WITH ranked AS (
 SELECT device_os, seconds_to_success,
 ROW_NUMBER() OVER(PARTITION BY device_os ORDER BY seconds_to_success) AS position,
 COUNT(*) OVER(PARTITION BY device_os) AS sample_size
 FROM fact_payment_attempt
 WHERE attempt_date >= '2026-08-01' AND attempt_date < '2026-09-26'
 AND seconds_to_success IS NOT NULL
)
SELECT device_os, MAX(sample_size) AS successful_attempts,
 AVG(seconds_to_success) AS median_journey_seconds
FROM ranked WHERE position IN ((sample_size+1)/2, (sample_size+2)/2) GROUP BY device_os;

-- name: daily
WITH RECURSIVE dates(day) AS (
 SELECT '2026-08-01' UNION ALL SELECT date(day,'+1 day') FROM dates WHERE day<'2026-09-25'
), daily AS (
 SELECT d.day AS attempt_date, COUNT(f.attempt_id) AS attempts,
 COALESCE(SUM(outcome='succeeded'),0) AS succeeded,
 COALESCE(SUM(submitted_at IS NOT NULL),0) AS submitted,
 COALESCE(SUM(outcome='failed'),0) AS failed
 FROM dates d LEFT JOIN fact_payment_attempt f ON f.attempt_date=d.day GROUP BY d.day
), rolling AS (
 SELECT *, SUM(attempts) OVER w AS rolling_attempts,
 SUM(succeeded) OVER w AS rolling_succeeded, COUNT(*) OVER w AS window_days
 FROM daily WINDOW w AS (ORDER BY attempt_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT *, ROUND(100.0*succeeded/NULLIF(attempts,0),2) AS completion_pct,
 ROUND(100.0*submitted/NULLIF(attempts,0),2) AS submission_pct,
 ROUND(100.0*failed/NULLIF(submitted,0),2) AS failure_pct,
 ROUND(100.0*rolling_succeeded/NULLIF(rolling_attempts,0),2) AS rolling_completion_pct
FROM rolling ORDER BY attempt_date;

-- name: join_check
SELECT (SELECT COUNT(*) FROM fact_payment_attempt) AS fact_rows,
 (SELECT COUNT(*) FROM fact_payment_attempt f LEFT JOIN support_cases s USING(attempt_id)) AS naive_join_rows,
 (SELECT COUNT(*) FROM fact_payment_attempt f JOIN customers c USING(customer_id)) AS customer_join_rows,
 (SELECT SUM(support_case_count) FROM fact_payment_attempt) AS linked_support_cases;

-- name: revision_query_plan
EXPLAIN QUERY PLAN SELECT * FROM raw_attempts WHERE attempt_id='A00001'
ORDER BY source_updated_at DESC, source_row_id DESC LIMIT 1;

-- name: date_query_plan
EXPLAIN QUERY PLAN SELECT COUNT(*) FROM fact_payment_attempt
WHERE attempt_date >= '2026-08-29' AND attempt_date < '2026-09-26';
