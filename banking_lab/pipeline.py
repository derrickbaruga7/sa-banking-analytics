"""Revision-aware SQLite ingestion and versioned CSV export; standard library only."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('attempt_id', 'customer_id', 'started_at', 'submitted_at',
          'app_version', 'device_os', 'amount_zar', 'source_updated_at')


def connect(path):
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize(connection):
    connection.executescript((ROOT / 'sql/model.sql').read_text())


def timestamp(value):
    if not isinstance(value, str) or len(value) < 19:
        raise ValueError('timestamp must include date, hours, minutes and seconds')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.microsecond:
        raise ValueError('timestamp precision must be whole seconds')
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime('%Y-%m-%d %H:%M:%S')


def normalize(record, customers):
    if not isinstance(record, dict) or set(record) != set(FIELDS):
        raise ValueError('invalid_schema')
    result = dict(record)
    for field in ('attempt_id', 'customer_id', 'app_version'):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError('invalid_' + field)
        result[field] = result[field].strip()
    if result['customer_id'] not in customers:
        raise ValueError('unknown_customer')
    for field in ('started_at', 'source_updated_at', 'submitted_at'):
        if field == 'submitted_at' and result[field] is None:
            continue
        try:
            result[field] = timestamp(result[field])
        except (ValueError, TypeError, OverflowError):
            raise ValueError('invalid_' + field) from None
    if result['submitted_at'] and result['submitted_at'] < result['started_at']:
        raise ValueError('submission_before_start')
    if result['source_updated_at'] < (result['submitted_at'] or result['started_at']):
        raise ValueError('revision_before_event')
    if isinstance(result['amount_zar'], bool) or not isinstance(result['amount_zar'], (int, float)):
        raise ValueError('invalid_amount')
    try:
        amount = Decimal(str(result['amount_zar']))
        if not amount.is_finite() or not 0 < amount <= Decimal('1000000000000'):
            raise ValueError('invalid_amount')
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError('amount_requires_whole_cents')
    except InvalidOperation:
        raise ValueError('invalid_amount') from None
    result['amount_zar'] = float(amount)
    os_name = result['device_os']
    if not isinstance(os_name, str) or os_name.strip().lower() not in ('android', 'ios'):
        raise ValueError('invalid_device_os')
    result['device_os'] = {'android': 'Android', 'ios': 'iOS'}[os_name.strip().lower()]
    return result


def canonical(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(records, customers):
    """Reject both sides of an in-batch conflict, independent of delivery order."""
    valid, rejected, versions = [], [], {}
    for position, raw in enumerate(records, 1):
        try:
            row = normalize(raw, customers)
            key = (row['attempt_id'], row['source_updated_at'])
            versions.setdefault(key, set()).add(canonical(row))
            valid.append((position, raw, row))
        except ValueError as error:
            rejected.append((position, raw, str(error)))
    accepted = []
    for position, raw, row in valid:
        if len(versions[(row['attempt_id'], row['source_updated_at'])]) > 1:
            rejected.append((position, raw, 'conflicting_batch_revision'))
        else:
            accepted.append((position, raw, row))
    # Consistent results even if a correction precedes its older delivery.
    accepted.sort(key=lambda item: (item[2]['attempt_id'], item[2]['source_updated_at']))
    return accepted, rejected


def load(connection, accepted, customers):
    counts = dict(inserted=0, revised=0, repeated=0, stale=0)
    conflicts = []
    for position, raw, row in accepted:
        existing = connection.execute(
            'SELECT ' + ','.join(FIELDS) + ' FROM raw_attempts WHERE attempt_id = ? '
            'ORDER BY source_updated_at DESC, source_row_id DESC LIMIT 1',
            (row['attempt_id'],)).fetchone()
        if existing:
            old = dict(existing)
            if row['source_updated_at'] < old['source_updated_at']:
                counts['stale'] += 1
                continue
            if row['source_updated_at'] == old['source_updated_at']:
                try:
                    identical = normalize(old, customers) == row
                except ValueError:
                    identical = old == row
                if identical:
                    counts['repeated'] += 1
                else:
                    conflicts.append((position, raw, 'conflicting_existing_revision'))
                continue
        connection.execute(
            'INSERT INTO raw_attempts (' + ','.join(FIELDS) + ') VALUES ('
            + ','.join('?' for _ in FIELDS) + ')', tuple(row[key] for key in FIELDS))
        counts['revised' if existing else 'inserted'] += 1
    return counts, conflicts


def reconcile(connection):
    latest, accepted, rejected = connection.execute('''
        SELECT COUNT(*), COALESCE(SUM(rejection_reason IS NULL),0),
        COALESCE(SUM(rejection_reason IS NOT NULL),0) FROM stg_attempt_validation
    ''').fetchone()
    facts, distinct_facts = connection.execute(
        'SELECT COUNT(*), COUNT(DISTINCT attempt_id) FROM fact_payment_attempt').fetchone()
    unique_source = connection.execute('SELECT COUNT(DISTINCT attempt_id) FROM raw_attempts').fetchone()[0]
    if not (latest == accepted + rejected == unique_source and facts == distinct_facts == accepted):
        raise RuntimeError('fact_grain_or_reconciliation_failed')
    return dict(latest=latest, accepted=accepted, rejected=rejected, fact_rows=facts)


def export_snapshot(connection, destination):
    queries = {
        'fact_payment_attempt': 'SELECT * FROM fact_payment_attempt ORDER BY attempt_id',
        'customers': 'SELECT * FROM customers ORDER BY customer_id',
        'support_cases': 'SELECT s.* FROM support_cases s JOIN fact_payment_attempt f '
                         'USING(attempt_id) ORDER BY s.case_id',
        'rejected_attempts': 'SELECT * FROM stg_attempt_validation '
                             'WHERE rejection_reason IS NOT NULL ORDER BY attempt_id',
    }
    files = {}
    for name, query in queries.items():
        cursor = connection.execute(query)
        path = destination / (name + '.csv')
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def reject_json_constant(value):
    raise ValueError('nonfinite_json')


def run_pipeline(database, batch, export_root):
    records = json.loads(Path(batch).read_text(encoding='utf-8'),
                         parse_constant=reject_json_constant)
    if not isinstance(records, list):
        raise ValueError('batch_must_be_a_json_array')
    export_root = Path(export_root)
    export_root.mkdir(parents=True, exist_ok=True)
    run_id, started = uuid.uuid4().hex, utc_now()
    temporary = Path(tempfile.mkdtemp(prefix='.pending-', dir=export_root))
    connection = None
    initialized = False
    committed = False
    try:
        connection = connect(database)
        initialize(connection)
        initialized = True
        connection.execute('BEGIN IMMEDIATE')
        customers = {r[0] for r in connection.execute('SELECT customer_id FROM customers')}
        accepted, rejected = validate(records, customers)
        counts, conflicts = load(connection, accepted, customers)
        rejected += conflicts
        counts['rejected'] = len(rejected)
        if sum(counts.values()) != len(records):
            raise RuntimeError('batch_reconciliation_failed')
        connection.executemany('INSERT INTO quarantine VALUES (?,?,?,?)', [
            (run_id, number, reason, json.dumps(raw, sort_keys=True))
            for number, raw, reason in rejected])
        totals = reconcile(connection)
        files = export_snapshot(connection, temporary)
        finished = utc_now()
        manifest = dict(run_id=run_id, started_at=started, finished_at=finished,
                        input_count=len(records), counts=counts, reconciliation=totals,
                        synthetic=True, files=files)
        (temporary / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        connection.execute('INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (run_id, started, finished, 'committed', len(records),
                            counts['inserted'], counts['revised'], counts['repeated'],
                            counts['stale'], counts['rejected'], None))
        connection.commit()
        committed = True
        snapshot = export_root / run_id
        os.replace(temporary, snapshot)
        pointer = export_root / ('.latest-' + run_id + '.json')
        pointer.write_text(json.dumps({'snapshot': run_id, 'manifest': run_id + '/manifest.json'}) + '\n')
        os.replace(pointer, export_root / 'latest.json')
        connection.execute('UPDATE ingestion_runs SET status = ? WHERE run_id = ?', ('succeeded', run_id))
        connection.commit()
        return manifest
    except Exception as error:
        if not initialized:
            raise
        connection.rollback()
        # Log the error class, never an input payload or arbitrary exception text.
        if committed:
            connection.execute('UPDATE ingestion_runs SET status=?, error=? WHERE run_id=?',
                               ('publish_failed', type(error).__name__, run_id))
        else:
            connection.execute('INSERT INTO ingestion_runs(run_id,started_at,finished_at,status,error) '
                               'VALUES (?,?,?,?,?)', (run_id, started, utc_now(), 'failed', type(error).__name__))
        connection.commit()
        raise
    finally:
        if connection is not None:
            connection.close()
        if temporary.exists():
            shutil.rmtree(temporary)
