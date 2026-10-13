import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from banking_lab.analysis import analyze
from banking_lab.generate import generate
from banking_lab.pipeline import connect, initialize, normalize, reconcile, run_pipeline, validate


class BankingLabTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = generate(self.root)
        self.batch = self.root / 'next_batch.json'
        self.exports = self.root / 'exports'
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        initialize(self.connection)
        self.records = json.loads(self.batch.read_text())
        self.customers = {r[0] for r in self.connection.execute('SELECT customer_id FROM customers')}

    def scalar(self, sql, args=()):
        return self.connection.execute(sql, args).fetchone()[0]

    def deliver(self, records):
        self.batch.write_text(json.dumps(records))
        return run_pipeline(self.database, self.batch, self.exports)

    def facts(self):
        return [tuple(row) for row in self.connection.execute('SELECT * FROM fact_payment_attempt ORDER BY attempt_id')]

    def test_seed_reconciliation_and_support_grain(self):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'), 6150)
        self.assertEqual(reconcile(self.connection), dict(latest=6000, accepted=5980, rejected=20, fact_rows=5980))
        self.assertGreater(self.scalar('SELECT COUNT(*) FROM fact_payment_attempt LEFT JOIN support_cases USING(attempt_id)'), 5980)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM fact_payment_attempt JOIN customers USING(customer_id)'), 5980)

    def test_first_load_correction_and_repeat_delivery(self):
        original_date = self.scalar("SELECT attempt_date FROM fact_payment_attempt WHERE attempt_id='A00001'")
        first = self.deliver(self.records)
        self.assertEqual(first['counts'], dict(inserted=20,revised=1,repeated=10,stale=0,rejected=0))
        facts = self.facts()
        raw_count = self.scalar('SELECT COUNT(*) FROM raw_attempts')
        second = self.deliver(self.records)
        self.assertEqual(second['counts'], dict(inserted=0,revised=0,repeated=30,stale=1,rejected=0))
        self.assertEqual(self.facts(), facts)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'), raw_count)
        self.assertEqual(self.scalar("SELECT amount_zar FROM fact_payment_attempt WHERE attempt_id='A00001'"), 250)
        self.assertEqual(self.scalar("SELECT attempt_date FROM fact_payment_attempt WHERE attempt_id='A00001'"), original_date)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM fact_payment_attempt WHERE attempt_date='2026-09-27' AND outcome='not_submitted'"), 20)

    def test_existing_revision_conflict_and_stale(self):
        conflict = dict(self.records[0], amount_zar=999)
        result = self.deliver([conflict])
        self.assertEqual(result['counts']['rejected'], 1)
        self.assertEqual(self.scalar('SELECT reason FROM quarantine'), 'conflicting_existing_revision')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'), 6150)

    def test_batch_conflicts_reject_both_orders(self):
        a = self.records[-1]
        b = dict(a, amount_zar=123)
        for records in ([a,b],[b,a]):
            accepted, rejected = validate(records,self.customers)
            self.assertEqual(accepted, [])
            self.assertEqual([r[2] for r in rejected], ['conflicting_batch_revision']*2)

    def test_validation_rejects_bad_payloads(self):
        base = self.records[-1]
        bad = [dict(base,customer_id='missing'), dict(base,started_at='2026-02-30 11:00:00'),
               dict(base,submitted_at='2026-09-26 11:00:00'), dict(base,amount_zar=-1),
               dict(base,amount_zar=0),dict(base,amount_zar=True),dict(base,amount_zar=0.001),
               dict(base,amount_zar=float('inf')),dict(base,device_os='other'),
               dict(base,source_updated_at='2026-09-26 00:00:00'),dict(base,extra='field'),None]
        accepted,rejected = validate(bad,self.customers)
        self.assertEqual(accepted,[])
        self.assertEqual(len(rejected),len(bad))

    def test_normalization_and_utc(self):
        row = dict(self.records[-1],device_os=' android ',started_at='2026-09-27T13:00:00+02:00')
        normalized = normalize(row,self.customers)
        self.assertEqual(normalized['device_os'],'Android')
        self.assertEqual(normalized['started_at'],'2026-09-27 11:00:00')

    def test_failed_insert_rolls_back_entire_batch(self):
        self.connection.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON raw_attempts WHEN NEW.attempt_id='A06002' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.deliver(self.records)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'),6150)
        self.assertEqual(self.scalar("SELECT status FROM ingestion_runs"),'failed')
        self.assertFalse((self.exports/'latest.json').exists())

    def test_failed_export_rolls_back_and_preserves_published_snapshot(self):
        self.deliver([])
        pointer = (self.exports/'latest.json').read_bytes()
        with patch('banking_lab.pipeline.export_snapshot',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.deliver(self.records)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'),6150)
        self.assertEqual((self.exports/'latest.json').read_bytes(),pointer)

    def test_publish_failure_can_be_retried_without_duplicate_load(self):
        with patch('banking_lab.pipeline.os.replace',side_effect=OSError('publication failure')):
            with self.assertRaises(OSError): self.deliver(self.records)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM raw_attempts'),6171)
        self.assertEqual(self.scalar('SELECT status FROM ingestion_runs'),'publish_failed')
        result = self.deliver(self.records)
        self.assertEqual(result['counts']['inserted'],0)
        self.assertTrue((self.exports/'latest.json').exists())

    def test_export_csv_headers_and_escaping(self):
        self.connection.execute('UPDATE customers SET segment=? WHERE customer_id=?',('Small, "quoted" business','C0001'))
        self.connection.commit()
        manifest = self.deliver([])
        with (self.exports/manifest['run_id']/'customers.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]['segment'],'Small, "quoted" business')

    def test_latest_invalid_revision_is_excluded_without_fallback(self):
        row = dict(self.records[0],source_updated_at='2026-09-28 00:00:00',amount_zar=-1)
        columns = ','.join(row)
        self.connection.execute('INSERT INTO raw_attempts('+columns+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
        self.connection.commit()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM fact_payment_attempt WHERE attempt_id='A00001'"),0)
        self.assertEqual(reconcile(self.connection)['rejected'],21)

    def test_sql_validation_rejects_invalid_calendar_date(self):
        self.connection.execute("UPDATE raw_attempts SET started_at='2026-02-30 00:00:00' WHERE attempt_id='A00001'")
        self.connection.commit()
        self.assertEqual(self.scalar("SELECT rejection_reason FROM stg_attempt_validation WHERE attempt_id='A00001'"),'invalid_start_time')

    def test_unresolved_backend_and_unsubmitted_are_distinct(self):
        self.connection.execute("DELETE FROM backend_payments WHERE attempt_id='A00001'")
        self.connection.execute("UPDATE raw_attempts SET submitted_at=datetime(started_at,'+10 seconds') WHERE attempt_id='A00001'")
        self.connection.commit()
        self.assertEqual(self.scalar("SELECT outcome FROM fact_payment_attempt WHERE attempt_id='A00001'"),'unresolved')

    def test_report_windows_rolling_medians_and_postload_comparability(self):
        from statistics import median
        before = analyze(self.database,self.root/'before')
        self.assertEqual(len(before['daily']),56)
        self.assertEqual(before['daily'][0]['window_days'],1)
        self.assertEqual(before['daily'][6]['window_days'],7)
        self.assertEqual(sum(p['attempts'] for p in before['periods']),5980)
        for result in before['median_duration']:
            seconds = [r[0] for r in self.connection.execute('SELECT seconds_to_success FROM fact_payment_attempt WHERE device_os=? AND seconds_to_success IS NOT NULL',(result['device_os'],))]
            self.assertEqual(result['median_journey_seconds'],median(seconds))
        self.deliver(self.records)
        after = analyze(self.database,self.root/'after')
        for name in ('periods','version_os','daily','segments','provinces','reasons'):
            self.assertEqual(before[name],after[name],name)

    def test_generator_refuses_to_overwrite(self):
        with self.assertRaises(FileExistsError): generate(self.root)


if __name__ == '__main__':
    unittest.main()
