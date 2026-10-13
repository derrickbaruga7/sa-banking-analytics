"""Deterministic fictional source data, adapted from the supplied guided lab."""

from pathlib import Path

def generate(destination):
    import sqlite3, random, json
    from pathlib import Path
    from datetime import datetime, timedelta
    r=random.Random(42)
    root=Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    path=root/'banking_lab.sqlite'
    if path.exists():
        raise FileExistsError('Database already exists. Choose a new workspace to regenerate.')
    c=sqlite3.connect(path)
    c.executescript('''
    CREATE TABLE customers(customer_id TEXT PRIMARY KEY, province TEXT, segment TEXT, opened_date TEXT);
    CREATE TABLE raw_attempts(source_row_id INTEGER PRIMARY KEY, attempt_id TEXT, customer_id TEXT, started_at TEXT, submitted_at TEXT, app_version TEXT, device_os TEXT, amount_zar REAL, source_updated_at TEXT);
    CREATE TABLE backend_payments(attempt_id TEXT PRIMARY KEY, status TEXT, failure_reason TEXT, completed_at TEXT);
    CREATE TABLE support_cases(case_id TEXT PRIMARY KEY, attempt_id TEXT, customer_id TEXT, opened_at TEXT, category TEXT);
    ''')
    for i in range(1,801):
     c.execute('INSERT INTO customers VALUES(?,?,?,?)',(f'C{i:04}',r.choice(['Gauteng','Western Cape','KwaZulu-Natal','Eastern Cape']),r.choice(['Everyday','Student','Small business']), '2025-01-01'))
    rows=[]; payments=[]; cases=[]
    base=datetime(2026,8,1)
    for i in range(1,6001):
     t=base+timedelta(days=r.randrange(56),seconds=r.randrange(86400)); os=r.choice(['Android','Android','iOS'])
     ver='2.0' if t>=datetime(2026,8,29) and r.random()<.72 else '1.9'
     customer=f'C{r.randrange(1,801):04}'
     submitted=r.random()>.10
     sub=t+timedelta(seconds=r.randrange(10,100)) if submitted else None
     row=(i,f'A{i:05}',customer,t.isoformat(' '),sub.isoformat(' ') if sub else None,ver,os,round(r.uniform(20,5000),2),(t+timedelta(minutes=5)).isoformat(' '))
     rows.append(row)
     if submitted:
      fail=r.random() < (.22 if ver=='2.0' and os=='Android' else .045)
      status='failed' if fail else 'succeeded'
      reason=r.choice(['timeout','timeout','insufficient_funds']) if fail else None
      complete=sub+timedelta(seconds=r.randrange(2,40))
      payments.append((f'A{i:05}',status,reason,complete.isoformat(' ')))
      if fail and r.random()<.4:
       for j in range(1,1+(2 if r.random()<.15 else 1)):
        cases.append((f'S{i:05}-{j}',f'A{i:05}',customer,(complete+timedelta(hours=2)).isoformat(' '),'payment_failure'))
    # Repeated delivery and an older revision: latest-record dedup is needed.
    for j,row in enumerate(rows[:120],6001):
     vals=list(row); vals[0]=j; rows.append(tuple(vals))
    for j,row in enumerate(rows[120:150],6121):
     vals=list(row); vals[0]=j; vals[6]=' android '; vals[8]='2026-07-31 12:00:00'; rows.append(tuple(vals))
    # Controlled validation issues in unique records.
    for idx in range(150,160):
     vals=list(rows[idx]); vals[2]='C9999'; rows[idx]=tuple(vals)
    for idx in range(160,165):
     vals=list(rows[idx]); vals[7]=-100; rows[idx]=tuple(vals)
    for idx in range(165,170):
     vals=list(rows[idx]); vals[3]=None; rows[idx]=tuple(vals)
    c.executemany('INSERT INTO raw_attempts VALUES(?,?,?,?,?,?,?,?,?)',rows)
    c.executemany('INSERT INTO backend_payments VALUES(?,?,?,?)',payments)
    c.executemany('INSERT INTO support_cases VALUES(?,?,?,?,?)',cases)
    c.commit(); c.close()
    # Separate unseen next-day batch for the pipeline exercise; contains overlap and correction.
    batch=[]
    for row in rows[:10]:
     d=dict(zip(['source_row_id','attempt_id','customer_id','started_at','submitted_at','app_version','device_os','amount_zar','source_updated_at'],row)); d.pop('source_row_id'); batch.append(d)
    d=batch[0].copy(); d['amount_zar']=250.0; d['source_updated_at']='2026-09-27 10:00:00'; batch.append(d)
    for i in range(6001,6021):
     batch.append(dict(attempt_id=f'A{i:05}',customer_id='C0001',started_at='2026-09-27 11:00:00',submitted_at=None,app_version='2.0',device_os='Android',amount_zar=75.0,source_updated_at='2026-09-27 11:05:00'))
    (root/'next_batch.json').write_text(json.dumps(batch,indent=2))
    return path
