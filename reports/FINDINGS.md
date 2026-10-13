# Payment journey investigation

**Synthetic portfolio exercise.** These are fictional customers and payments, not observations about a real bank. Generated from `sql/analysis.sql`; no hand-entered performance values.

## Finding

Completion fell from **85.64%** before the release to **78.02%** after it. Submission was 89.73% before and 89.27% after. The pattern points toward investigating execution after submission.

In the same post-release period, Android 2.0 had **282 failures from 1294 submitted attempts (21.79%)**, compared with 4.69% for Android 1.9. The Android 2.0 group includes 233 customers with at least one failed attempt and 135 support cases across 117 attempts.

## Comparable groups

Baseline: August 1–28, 2026. Post-release: August 29–September 25, 2026. Both cover 28 calendar days. The September 27 pipeline batch is excluded from these comparisons.

| Version | OS | Started | Submitted | Failed | Failed / submitted | Affected customers | Support cases |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.0 | Android | 1,453 | 1,294 | 282 | 21.79% | 233 | 135 |
| 1.9 | iOS | 278 | 246 | 13 | 5.28% | 13 | 10 |
| 1.9 | Android | 570 | 512 | 24 | 4.69% | 24 | 10 |
| 2.0 | iOS | 747 | 669 | 24 | 3.59% | 24 | 6 |

Android 2.0 failure reasons: 187 timeout (14.45% of submitted attempts), 95 insufficient_funds (7.34% of submitted attempts).

## Interpretation and next investigation

The rollout is observational. Version adoption, device/network differences, traffic, or backend conditions may explain part of the difference. Repeated attempts by the same customer are not independent observations. These descriptive rates do not establish a causal release effect.

Investigate Android 2.0 request traces, timeout handling, retry behavior, and backend outcomes. Compare like-for-like devices, networks, time windows, and customer activity. Insufficient funds requires a separate journey/messaging investigation. The dataset cannot test app success-event tracking, individual screen abandonment, API-only latency, or a post-fix improvement.

## Proposed acceptance criteria

- Preserve request/attempt correlation through submission, backend outcome, retry, and support investigation; verify that retries cannot duplicate a payment.
- Reconcile released-product telemetry with backend outcomes and retain unresolved outcomes separately.
- Agree a practical failure-rate improvement target before a controlled rollout, with submission rate, completion, support demand, and duplicate-payment checks as guardrails.
- Measure the change over comparable periods; account for repeated customers and report uncertainty. No fix or production improvement has been measured in this lab.

## Data quality and definitions

The current source contains 6,020 unique attempts: 6,000 accepted and 20 excluded. All reported rates use accepted attempts within the stated period. Rejections are preserved for review.

- Completion = backend successes / accepted started attempts.
- Submission = submitted / accepted started attempts.
- Submitted failure = backend failures / submitted attempts.
- Unresolved = submitted but without a recognized final backend outcome; never treated as success.
- Support contact = attempts with at least one case / accepted started attempts.
- Successful journey duration = backend completion minus journey start; includes customer interaction and excludes unsuccessful journeys.
- Rolling completion = summed successes / summed attempts over seven calendar dates. The first six points use shorter windows.

Support is aggregated to one row per attempt before joining. A direct support join gives 6,029 rows versus 6,000 facts, demonstrating why grain matters. Provincial and customer-segment attributes are random fictional assignments.

## Reproduce and inspect

Run `python -m banking_lab demo --workspace build`. Review the CSVs next to this file, `analysis.json`, and `index.html`. `segments.csv`, `provinces.csv`, `repeated_failures.csv`, and `median_duration.csv` complete the independent SQL exercises. Query plans are recorded without claiming a measured speedup.
