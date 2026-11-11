import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from .config import ConversionError

TERMINAL = ('ready', 'needs_review', 'failed', 'cancelled', 'expired')


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = settings.root/'jobs.sqlite3'
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, state TEXT NOT NULL,
                mode TEXT NOT NULL, language TEXT NOT NULL, created REAL NOT NULL,
                updated REAL NOT NULL, expires REAL NOT NULL, error TEXT, report TEXT,
                provider_job TEXT)''')

    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def create(self, mode, language):
        now, token, job_id = time.time(), secrets.token_urlsafe(32), uuid.uuid4().hex
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            count = c.execute("SELECT count(*) FROM jobs WHERE state IN ('uploading','queued','processing','validating')").fetchone()[0]
            if count >= self.settings.max_queue:
                raise ConversionError('queue_full')
            c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                      (job_id, hashlib.sha256(token.encode()).hexdigest(), 'uploading', mode, language,
                       now, now, now+self.settings.retention_seconds, None, None, None))
        (self.settings.root/job_id).mkdir(mode=0o700)
        return job_id, token

    def get(self, job_id, token=None):
        with self.connect() as c:
            row = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            return None
        if token is not None and not secrets.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            return None
        return dict(row)

    def update(self, job_id, state, allowed, **values):
        assert set(values) <= {'error', 'report', 'provider_job'}
        fields = {'state':state, 'updated':time.time(), **values}
        with self.connect() as c:
            result = c.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in fields)} WHERE id=? AND state IN ({','.join('?' for _ in allowed)})",
                               (*fields.values(), job_id, *allowed))
            return result.rowcount == 1

    def claim(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT id FROM jobs WHERE state='queued' AND expires>? ORDER BY created LIMIT 1", (time.time(),)).fetchone()
            if row:
                c.execute("UPDATE jobs SET state='processing', updated=? WHERE id=?", (time.time(), row['id']))
                return row['id']

    def cleanup(self):
        import shutil
        now = time.time()
        with self.connect() as c:
            rows = c.execute("SELECT id FROM jobs WHERE expires<? OR state IN ('cancelled','expired')", (now,)).fetchall()
            c.execute("UPDATE jobs SET state='expired' WHERE expires<? AND state!='cancelled'", (now,))
            # Never automatically resubmit ambiguous paid jobs after a worker crash.
            c.execute("UPDATE jobs SET state='failed',error='worker_interrupted',updated=? WHERE state IN ('processing','validating','uploading') AND updated<?",
                      (now, now-self.settings.job_timeout-60))
        for row in rows:
            shutil.rmtree(self.settings.root/row['id'], ignore_errors=True)

    @staticmethod
    def public(row):
        return {k: (json.loads(row[k]) if row[k] and k == 'report' else row[k])
                for k in ('id','state','mode','created','expires','error','report')}
