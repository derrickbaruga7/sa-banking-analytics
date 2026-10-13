-- SQLite. Canonical timestamps are UTC: YYYY-MM-DD HH:MM:SS.
CREATE INDEX IF NOT EXISTS ix_raw_revision
ON raw_attempts(attempt_id, source_updated_at DESC, source_row_id DESC);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL, input_count INTEGER, inserted INTEGER, revised INTEGER,
    repeated INTEGER, stale INTEGER, rejected INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS quarantine (
    run_id TEXT NOT NULL, record_number INTEGER NOT NULL, reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(run_id, record_number)
);

DROP VIEW IF EXISTS fact_payment_attempt;
DROP VIEW IF EXISTS stg_attempt_validation;
DROP VIEW IF EXISTS stg_latest_attempts;

CREATE VIEW stg_latest_attempts AS
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY attempt_id
        ORDER BY source_updated_at DESC, source_row_id DESC
    ) AS revision_rank FROM raw_attempts
)
SELECT source_row_id, attempt_id, customer_id, started_at, submitted_at,
    app_version,
    CASE LOWER(TRIM(device_os))
        WHEN 'android' THEN 'Android' WHEN 'ios' THEN 'iOS' ELSE 'Unknown'
    END AS device_os,
    amount_zar, source_updated_at
FROM ranked WHERE revision_rank = 1;

CREATE VIEW stg_attempt_validation AS
SELECT a.*, CASE
    WHEN attempt_id IS NULL OR TRIM(attempt_id) = '' THEN 'invalid_attempt_id'
    WHEN started_at IS NULL OR length(started_at) != 19
        OR datetime(started_at, '+0 days') IS NULL
        OR datetime(started_at, '+0 days') != started_at THEN 'invalid_start_time'
    WHEN submitted_at IS NOT NULL AND (
        length(submitted_at) != 19 OR datetime(submitted_at, '+0 days') IS NULL
        OR datetime(submitted_at, '+0 days') != submitted_at
        OR submitted_at < started_at) THEN 'invalid_submission_time'
    WHEN source_updated_at IS NULL OR length(source_updated_at) != 19
        OR datetime(source_updated_at, '+0 days') IS NULL
        OR datetime(source_updated_at, '+0 days') != source_updated_at
        OR source_updated_at < COALESCE(submitted_at, started_at)
        THEN 'invalid_revision_time'
    WHEN typeof(amount_zar) NOT IN ('integer', 'real')
        OR amount_zar <= 0 OR amount_zar > 1000000000000
        THEN 'invalid_amount'
    WHEN c.customer_id IS NULL THEN 'unknown_customer'
    WHEN app_version IS NULL OR TRIM(app_version) = '' THEN 'invalid_app_version'
    WHEN device_os = 'Unknown' THEN 'invalid_device_os'
    ELSE NULL END AS rejection_reason
FROM stg_latest_attempts a LEFT JOIN customers c USING(customer_id);

CREATE VIEW fact_payment_attempt AS
WITH support AS (
    SELECT attempt_id, COUNT(*) AS support_case_count
    FROM support_cases GROUP BY attempt_id
)
SELECT a.attempt_id, a.customer_id, c.province, c.segment,
    date(a.started_at) AS attempt_date, a.started_at, a.submitted_at,
    a.app_version, a.device_os, a.amount_zar,
    CASE WHEN a.submitted_at IS NULL THEN 'not_submitted'
        WHEN b.status = 'succeeded' THEN 'succeeded'
        WHEN b.status = 'failed' THEN 'failed'
        ELSE 'unresolved' END AS outcome,
    CASE WHEN a.submitted_at IS NOT NULL AND b.status = 'failed'
        THEN b.failure_reason END AS failure_reason,
    b.completed_at,
    CASE WHEN a.submitted_at IS NOT NULL AND b.status = 'succeeded'
        AND datetime(b.completed_at) >= datetime(a.submitted_at)
        THEN ROUND((julianday(b.completed_at)-julianday(a.started_at))*86400, 2)
    END AS seconds_to_success,
    COALESCE(s.support_case_count, 0) AS support_case_count
FROM stg_attempt_validation a
JOIN customers c USING(customer_id)
LEFT JOIN backend_payments b USING(attempt_id)
LEFT JOIN support s USING(attempt_id)
WHERE a.rejection_reason IS NULL;
