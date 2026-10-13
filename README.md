# South African banking analytics

A completed SQL and Python investigation of a fictional bank's mobile payment journey, with a reproducible pipeline and a browser dashboard.

**All data is synthetic.** This is a portfolio exercise, not an assessment of a real bank. It builds on the supplied South African Banking Guided Lab; the source generator retains its seed and scenario. The implementation, tests, and findings complete the exercise.

## The question

Customers may be struggling to complete payments. Is there a measurable problem, who is affected, and what should the product team investigate next?

In the generated scenario, completion falls from **85.64% to 78.02%** across two equal 28-day windows. Android 2.0 records **282 failures / 1,294 submitted attempts (21.79%)**, compared with **4.69%** for Android 1.9 in the same post-release window. This is an observed association, not proof that the release caused the difference.

- [Read the findings and proposed acceptance criteria](reports/FINDINGS.md).
- [Download the self-contained dashboard](reports/index.html), then open it in a browser. GitHub displays the HTML source rather than hosting the interactive page.
- [Inspect the SQL analysis](sql/analysis.sql) and [pipeline](banking_lab/pipeline.py).

## Run it

Requires **Python 3.11 or newer**. No third-party packages, accounts, credentials, or external data downloads are needed. Run commands from the repository root.

```bash
python -m unittest discover -s tests -v
python -m banking_lab demo --workspace build
```

Use `python3` if that is your Python command. Open `build/report/index.html` in a browser. The demo generates the source database, analyzes the baseline, loads the later batch twice, exports CSV snapshots, and regenerates the report.

The generator refuses to overwrite an existing database. For another complete run, use a different workspace, for example `--workspace build-fresh`.

Individual stages:

```bash
python -m banking_lab generate --workspace work-data
python -m banking_lab analyze --database work-data/banking_lab.sqlite --output work-data/baseline
python -m banking_lab ingest --database work-data/banking_lab.sqlite --batch work-data/next_batch.json --exports work-data/exports
python -m banking_lab analyze --database work-data/banking_lab.sqlite --output work-data/report
```

## What is implemented

| Layer | Work |
| --- | --- |
| Source | Seeded generator: 800 fictional customers, 6,000 unique attempts, repeated deliveries, stale revisions, and 20 intentionally invalid attempts. |
| SQL | Latest-revision selection; validation; one accepted attempt per fact; explicit metric denominators; comparable cohorts; support aggregation; calendar-aware rolling rates; median durations; query plans. |
| Python | Strict JSON validation, UTC normalization, append-only revisions, duplicate/stale delivery handling, conflict quarantine, transactions, reconciliation, run history, and versioned CSV exports. |
| Reporting | Self-contained HTML dashboard, generated findings, JSON evidence, and CSV results for each named query. |
| Verification | Regression tests for counts, grain, revisions, malformed inputs, conflict order, rollback, publication recovery, CSV quoting, medians, and reporting windows. GitHub Actions runs tests and the full demo. |
| Power BI | CSV exports, a model specification, and DAX measures ready for import; see [the handoff](docs/power-bi.md). |

## Expected reconciliation

| Check | Baseline | After the later batch |
| --- | ---: | ---: |
| Delivered raw rows | 6,150 | 6,171 |
| Unique latest attempts | 6,000 | 6,020 |
| Accepted facts | 5,980 | 6,000 |
| Excluded latest attempts | 20 | 20 |

First batch: 20 inserts, one historical revision, 10 repeated deliveries. Repeat batch: no inserts or revisions; 30 repeated and one stale delivery. Audit records may grow on a retry; logical facts do not.

The analysis window is **August 1–September 25, 2026**. The later batch adds September 27 attempts, so it is excluded from release comparisons. The historical amount correction preserves the attempt's original date.

## Design decisions and limits

- A fact represents one accepted attempt. Backend outcomes determine success or failure; missing or unrecognized outcomes remain unresolved. Support cases are aggregated before joining.
- Equal revision timestamps with different payloads are quarantined. The initial seed's deterministic tie-break is safe only because its repeated latest payloads agree. See [the data contract](docs/data-contract.md).
- Exports are immutable run directories. Read `exports/latest.json` once, then use the snapshot it names. The database and filesystem cannot share one atomic transaction; a publication failure after commit is recorded and a retry safely republishes. See [operations](docs/operations.md).
- This is a single-writer local lab. It does not process money, provide a financial ledger, or connect to bank accounts. REAL-valued amounts and SQLite are appropriate to the supplied analytics exercise, not a production ledger design.
- The browser report is complete. Power BI Desktop execution and cloud deployment are separate follow-ups; no PBIX, live refresh, AWS infrastructure, or measured production improvement is claimed.

## Repository map

```text
banking_lab/       generator, ingestion, analysis, dashboard template, CLI
sql/              reporting model and named analytical queries
tests/            standard-library regression tests
reports/          generated synthetic findings, dashboard, JSON, and query CSVs
docs/             data contract, Power BI handoff, operations, decision log
.github/workflows/ continuous integration
```

Generated working databases, input batches, export snapshots, and local environments are ignored. The committed report contains only reproducible synthetic results.
