# Data contract

The supplied lab defines a fictional mobile-payment dataset. No real customer names, credentials, account numbers, or source exports are included.

| Entity | Grain | Key |
| --- | --- | --- |
| customers | One fictional customer | customer_id |
| raw_attempts | One delivered full revision of an attempt | source_row_id; business key attempt_id |
| backend_payments | At most one backend outcome per attempt | attempt_id |
| support_cases | One case; an attempt may have several | case_id |
| fact_payment_attempt | One accepted latest attempt | attempt_id |

Incoming JSON must be an array of objects with exactly these fields: `attempt_id`, `customer_id`, `started_at`, `submitted_at`, `app_version`, `device_os`, `amount_zar`, and `source_updated_at`. Only `submitted_at` may be null.

IDs and version are nonempty strings. Customer IDs must already exist. OS is normalized from Android/iOS spellings with optional whitespace. Timestamps have whole-second precision; explicit offsets are converted to UTC and naive timestamps are interpreted as UTC, matching the lab contract. Submission cannot precede start, and source revision cannot precede the latest event in its snapshot.

Amounts are JSON numbers, strictly positive, at most ZAR 1 trillion, and represent whole cents. Booleans, nonfinite numbers, and fractional cents are rejected. This upper bound is an input guard for the demo, not a bank policy. Amounts remain SQLite REAL to preserve the source schema; no money movement or accounting arithmetic is implemented.

## Revision policy

Validate before loading. Within a batch, conflicting payloads for the same attempt and revision timestamp are all quarantined, regardless of order. Otherwise process each attempt in revision order:

1. New attempt: insert.
2. Newer revision: append; retain history.
3. Same timestamp and identical normalized payload: repeated delivery; skip.
4. Older than current latest: stale; skip.
5. Same current timestamp and different payload: conflict; quarantine.

`source_updated_at` is source time. Ingestion-run timestamps are recorded separately. The seed includes 120 identical repeats and 30 stale revisions; it does not contain conflicting latest snapshots. Existing historical seed conflicts would require an additional remediation policy before using this model elsewhere.

The SQL layer independently validates the latest seed records, preserving invalid records outside reporting. It never silently falls back to an older valid record when the latest record is invalid. The first matching rejection reason is reported. New input validation additionally enforces schema, timestamp normalization, and cent precision.

Backend and customer tables are fixed reference sources in this lab. Backend statuses `succeeded` and `failed` are final; other/missing submitted outcomes are unresolved. A future backend ingestion path needs its own contract and chronology checks. A successful journey duration is null when completion precedes submission.

## Denominators

Completion uses accepted starts; submitted failure uses accepted submitted attempts; reason rates use the same submitted population for each version/OS group. Support-contact rates count attempts with support, not case counts. Affected customers are distinct within each selected group and cannot be summed across groups.

Release comparisons are fixed to August 1–28 versus August 29–September 25. Provincial and segment results are descriptive synthetic slices. Repeated customers, selection into versions, and missing device/network covariates prevent a causal interpretation.
