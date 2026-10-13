"""Execute named SQL investigations and write auditable report artifacts."""
import csv
import json
from pathlib import Path
import re

from .pipeline import ROOT, connect, initialize, reconcile


def analyze(database, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    connection = connect(database)
    try:
        initialize(connection)
        data = {'synthetic': True, 'period_start': '2026-08-01',
                'period_end': '2026-09-25', 'reconciliation': reconcile(connection)}
        blocks = re.split(r'^-- name: (\w+)\s*$', (ROOT / 'sql/analysis.sql').read_text(), flags=re.M)
        for name, sql in zip(blocks[1::2], blocks[2::2]):
            cursor = connection.execute(sql.strip())
            columns = [item[0] for item in cursor.description]
            rows = [dict(row) for row in cursor]
            data[name] = rows
            with (destination / (name + '.csv')).open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
    finally:
        connection.close()
    (destination / 'analysis.json').write_text(json.dumps(data, indent=2) + '\n')
    (destination / 'FINDINGS.md').write_text(findings(data))
    template = (ROOT / 'banking_lab/dashboard.html').read_text()
    (destination / 'index.html').write_text(template.replace('__REPORT_DATA__',
        json.dumps(data).replace('<', '\\u003c')))
    return data


def findings(data):
    before, after = data['periods']
    groups = data['version_os']
    target = next(r for r in groups if r['app_version']=='2.0' and r['device_os']=='Android')
    comparison = next(r for r in groups if r['app_version']=='1.9' and r['device_os']=='Android')
    reasons = [r for r in data['reasons'] if r['app_version']=='2.0' and r['device_os']=='Android']
    rows = '\n'.join(f"| {r['app_version']} | {r['device_os']} | {r['attempts']:,} | {r['submitted']:,} | {r['failed']:,} | {r['failure_pct']:.2f}% | {r['affected_customers']} | {r['support_cases']} |" for r in groups)
    reason_text = ', '.join(f"{r['failures']} {r['failure_reason']} ({r['submitted_reason_pct']:.2f}% of submitted attempts)" for r in reasons)
    return f'''# Payment journey investigation

**Synthetic portfolio exercise.** These are fictional customers and payments, not observations about a real bank. Generated from `sql/analysis.sql`; no hand-entered performance values.

## Finding

Completion fell from **{before['completion_pct']:.2f}%** before the release to **{after['completion_pct']:.2f}%** after it. Submission was {before['submission_pct']:.2f}% before and {after['submission_pct']:.2f}% after. The pattern points toward investigating execution after submission.

In the same post-release period, Android 2.0 had **{target['failed']} failures from {target['submitted']} submitted attempts ({target['failure_pct']:.2f}%)**, compared with {comparison['failure_pct']:.2f}% for Android 1.9. The Android 2.0 group includes {target['affected_customers']} customers with at least one failed attempt and {target['support_cases']} support cases across {target['supported_attempts']} attempts.

## Comparable groups

Baseline: August 1–28, 2026. Post-release: August 29–September 25, 2026. Both cover 28 calendar days. The September 27 pipeline batch is excluded from these comparisons.

| Version | OS | Started | Submitted | Failed | Failed / submitted | Affected customers | Support cases |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}

Android 2.0 failure reasons: {reason_text}.

## Interpretation and next investigation

The rollout is observational. Version adoption, device/network differences, traffic, or backend conditions may explain part of the difference. Repeated attempts by the same customer are not independent observations. These descriptive rates do not establish a causal release effect.

Investigate Android 2.0 request traces, timeout handling, retry behavior, and backend outcomes. Compare like-for-like devices, networks, time windows, and customer activity. Insufficient funds requires a separate journey/messaging investigation. The dataset cannot test app success-event tracking, individual screen abandonment, API-only latency, or a post-fix improvement.

## Proposed acceptance criteria

- Preserve request/attempt correlation through submission, backend outcome, retry, and support investigation; verify that retries cannot duplicate a payment.
- Reconcile released-product telemetry with backend outcomes and retain unresolved outcomes separately.
- Agree a practical failure-rate improvement target before a controlled rollout, with submission rate, completion, support demand, and duplicate-payment checks as guardrails.
- Measure the change over comparable periods; account for repeated customers and report uncertainty. No fix or production improvement has been measured in this lab.

## Data quality and definitions

The current source contains {data['reconciliation']['latest']:,} unique attempts: {data['reconciliation']['accepted']:,} accepted and {data['reconciliation']['rejected']} excluded. All reported rates use accepted attempts within the stated period. Rejections are preserved for review.

- Completion = backend successes / accepted started attempts.
- Submission = submitted / accepted started attempts.
- Submitted failure = backend failures / submitted attempts.
- Unresolved = submitted but without a recognized final backend outcome; never treated as success.
- Support contact = attempts with at least one case / accepted started attempts.
- Successful journey duration = backend completion minus journey start; includes customer interaction and excludes unsuccessful journeys.
- Rolling completion = summed successes / summed attempts over seven calendar dates. The first six points use shorter windows.

Support is aggregated to one row per attempt before joining. A direct support join gives {data['join_check'][0]['naive_join_rows']:,} rows versus {data['join_check'][0]['fact_rows']:,} facts, demonstrating why grain matters. Provincial and customer-segment attributes are random fictional assignments.

## Reproduce and inspect

Run `python -m banking_lab demo --workspace build`. Review the CSVs next to this file, `analysis.json`, and `index.html`. `segments.csv`, `provinces.csv`, `repeated_failures.csv`, and `median_duration.csv` complete the independent SQL exercises. Query plans are recorded without claiming a measured speedup.
'''
