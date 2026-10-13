# Decisions and follow-up

| Decision | Reason |
| --- | --- |
| Preserve the supplied generator's seed and scenario | Keeps the completed work traceable to the original lab. |
| Use Python's standard library | The project runs without a package installation or external service. |
| Keep initial and later reporting windows separate | Unsubmitted September 27 activity would otherwise change the release comparison. |
| Include backend failures and unresolved outcomes separately | Missing final outcomes are not evidence of success. |
| Quarantine equal-version conflicts | An arbitrary delivery-order winner can hide data disagreement. |
| Use a calendar spine for rolling metrics | Seven observed rows need not represent seven calendar days. |
| Keep immutable export snapshots behind a pointer | Prevents consumers from seeing partly written files or mixed run exports. |
| Index the revision lookup | Supports per-attempt newest-revision reads; no measured speedup is claimed for this small dataset. |

## Completed

Source inspection; deduplication; validation; grain and denominator checks; period, version/OS, segment, province, support and repeat-failure analysis; median journey duration; query-plan inspection; findings and acceptance criteria; browser dashboard; ingestion, audit, quarantine and exports; rollback/retry tests; CI configuration.

## Follow-up backlog

1. Import the published snapshot into Power BI, apply the supplied model/measures, and reconcile the totals and one filtered group against the generated CSVs. Deliver a validated PBIX only after this check.
2. If cloud execution is needed, migrate to PostgreSQL and prove equivalent tests locally before provisioning infrastructure.
3. If extending beyond the lab, validate backend/customer feeds and introduce revision conflict checks for the entire historical source, not just new batches.
4. If testing a product intervention, define a controlled rollout, practical effect threshold, observation windows, and customer-clustered uncertainty before analyzing post-fix outcomes.

None of these follow-ups is presented as deployed or measured work.
