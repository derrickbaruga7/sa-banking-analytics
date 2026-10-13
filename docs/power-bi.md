# Power BI handoff

The SQL pipeline and browser dashboard are complete and tested. This handoff supplies the import model and measures; they have not been executed in Power BI Desktop, and no PBIX or cloud refresh is claimed.

## Import a consistent snapshot

Run the demo, read `build/exports/latest.json`, and use the run folder named by its `snapshot` value for every import. In Power BI Desktop, choose Get Data → Text/CSV, then import `fact_payment_attempt.csv`, `customers.csv`, and `support_cases.csv` from that one folder. Set encoding to UTF-8 and review inferred types. This follows Microsoft's [Text/CSV connector guidance](https://learn.microsoft.com/en-us/power-query/connectors/text-csv).

Set IDs, OS, versions, province, segment, outcome and reason to Text; `attempt_date` and `opened_date` to Date; timestamps to Date/Time; amount and duration to Decimal Number; support_case_count to Whole Number. Treat empty submitted/completed timestamps and durations as null. Do not convert a missing outcome into success.

Relationships, single-direction:

- `customers[customer_id]` 1 → * `fact_payment_attempt[customer_id]`.
- `fact_payment_attempt[attempt_id]` 1 → * `support_cases[attempt_id]`.
- A marked date table `DimDate[Date]` 1 → * `fact_payment_attempt[attempt_date]`.

Do not also connect customers directly to support. Use province and segment from the customer dimension; hide the duplicated fact attributes in report view. Review [Microsoft's relationship guidance](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships).

Create the calculated table:

```dax
DimDate = CALENDAR(DATE(2026, 8, 1), DATE(2026, 9, 27))
```

Add the measures in [measures.dax](measures.dax) one at a time. Rate measures deliberately ignore direct outcome and failure-reason filters while retaining cohort/date filters. This uses [CALCULATE's filter modifiers](https://learn.microsoft.com/en-us/dax/calculate-function-dax). Use raw failure counts for reason-level charts. Format rate measures as percentages without multiplying by 100.

## Report pages

1. Overview: attempts, submission, completion, submitted failure, unresolved, and affected-customer cards; daily completion; explicit reporting window and exclusions.
2. Release investigation: post-release version/OS table; failure reasons; supported attempts and case counts; province and segment slicers.
3. Data checks: accepted/excluded reconciliation, refresh snapshot ID, and SQL comparison table.

The overview's initial date filter is August 1–September 25. The release page is August 29–September 25. Keep September 27 visible only on an explicitly separate refresh/operations view.

## Acceptance checks before publishing a PBIX

- The complete exported fact has 6,000 rows after the demo; 5,980 fall inside the investigation window.
- Compare before/after counts and rates with `reports/periods.csv`.
- Filter Android 2.0 to August 29–September 25: 1,453 starts, 1,294 submissions, 282 failures, 233 affected customers, 135 support cases.
- Compare daily values with `reports/daily.csv`; never average daily percentages for a total.
- Select one province/segment and reconcile it to the corresponding SQL output.
- Check the rate measures under outcome/reason filters and verify that their denominators remain the defined cohort. Avoid bidirectional relationships and direct row-ID slicers.

These are acceptance targets from executed SQL, not a claim that Power BI already passed them.
