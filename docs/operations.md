# Run and recover

Run the pipeline locally with a single writer. Input batches and generated database files stay outside Git. Start from `python -m banking_lab demo --workspace build` for a reproducible synthetic demonstration.

Each ingestion uses `BEGIN IMMEDIATE`, parameterized inserts, full-batch reconciliation, and a committed audit record. Validation failures go to `quarantine`; load or export exceptions fail the run. Invalid JSON fails before loading. Exceptions propagate so a calling scheduler receives a nonzero process exit.

CSV files are written with headers and proper quoting into a temporary directory. After reconciliation and export preparation, the database transaction commits. The directory is then published under its unique run ID and `latest.json` is replaced atomically. Consumers must read the pointer once and load every CSV from that same snapshot. Manifests include SHA-256 hashes for verification.

- Failure before commit: raw inserts, corrections, and quarantine changes roll back. The previously published snapshot remains available. A separate failed audit row records the error class.
- Failure after database commit: the run is marked `publish_failed`; a snapshot might already exist, or the pointer might already have been published. Retry the same batch. Revision checks prevent duplicate facts, and the new export reflects the committed data.
- Process termination can leave a `.pending-*` directory or an audit status of `committed`. Do not promote these blindly. Restart the same batch, verify the newest successful manifest, and remove orphan artifacts only after review.
- Do not run overlapping jobs. SQLite serializes the database write transaction, but the whole export-publication workflow is not a distributed lock. Production orchestration must prevent overlap.

Inspect `ingestion_runs` for input counts, inserts, revisions, repeats, stale records, rejection counts, status, and timestamps. Logs returned by the CLI contain counts and hashes, not row-level payloads. Quarantine preserves original input locally for diagnosis.

## Future deployment

The completed deliverable is local SQLite/Python plus a browser report. The original lab also outlined an optional AWS/PostgreSQL extension; no resources were provisioned and no costs were incurred by this project.

Before deployment, migrate and test the SQL dialect; introduce managed secrets, ingestion access controls, a real single-writer lease, retention, backup/restore tests, freshness monitoring, and a validated reporting connection. Design monetary storage separately if the scope ever includes accounting. Review current platform documentation and costs before choosing infrastructure.

## Validation gates

- Latest records reconcile to accepted plus rejected.
- Facts are unique and equal accepted latest attempts.
- Support and customer joins preserve fact grain.
- Batch dispositions sum to input records.
- Repeating the supplied batch preserves logical results.
- A correction changes the intended revision and retains the original attempt date.
- Forced insert/export failures roll back; publication failures are safely retried.
- The 56-day analytical comparison is unchanged by the later 20 unsubmitted attempts.

These gates are covered by the regression suite. Power BI reconciliation and cloud recovery remain unexecuted follow-ups.
