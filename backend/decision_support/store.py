"""SQLite persistence with revision checks and idempotent mutations."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .playbook import default_preferences


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def public_session(session):
    return {**{key: value for key, value in session.items() if not key.startswith("_")},
            "preferences": session.get("preferences", default_preferences()),
            "can_undo": bool(session.get("_undo"))}


class SessionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mutations (session_id TEXT NOT NULL, mutation_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, PRIMARY KEY (session_id, mutation_id));
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def list(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT body FROM sessions ORDER BY updated_at DESC").fetchall()
        return [public_session(json.loads(row[0])) for row in rows]

    def get(self, session_id):
        with self.connect() as connection:
            row = connection.execute("SELECT body FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError("Session not found")
        return json.loads(row[0])

    def create(self, state, preferences=None):
        session = dict(id=uuid.uuid4().hex, revision=0, state=state, drive=1, status="active",
                       plays=[], queue=[], preferences=preferences if preferences is not None else default_preferences(),
                       created_at=now(), updated_at=now(), _undo=None)
        with self.connect() as connection:
            connection.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                               (session["id"], json.dumps(session), session["updated_at"]))
        return session

    def stage_historical(self, game_id, plays):
        session_id = 'history-' + hashlib.sha256(game_id.encode()).hexdigest()[:24]
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT body FROM sessions WHERE id=?', (session_id,)).fetchone()
            session = json.loads(row[0]) if row else dict(id=session_id, revision=0, state=plays[0]['before'],
                drive=1, status='review_only', mode='historical_review', source_game_id=game_id,
                preferences=default_preferences(), plays=[], queue=[], created_at=now(), updated_at=now(), _undo=None)
            existing = {play['id']: play for play in session['plays']}
            added = []
            for play in plays:
                if play['id'] in existing:
                    if existing[play['id']].get('source_sha256') != play['source_sha256']:
                        raise Conflict('Source data changed for a staged play. Resolve its provenance before importing again.')
                else:
                    added.append(play)
            if not added:
                return session
            session['plays'] = sorted(session['plays'] + added, key=lambda play: int(play['historical_source']['play_id']))
            session['revision'] += 1
            session['updated_at'] = now()
            connection.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)',
                               (session_id, json.dumps(session), session['updated_at']))
        return session

    def mutate(self, session_id, payload, operation, apply):
        mutation_id, revision = payload.get("mutation_id"), payload.get("revision")
        if not isinstance(mutation_id, str) or not 8 <= len(mutation_id) <= 100:
            raise ValueError("A mutation_id of 8–100 characters is required")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("A nonnegative session revision is required")
        fingerprint = hashlib.sha256(json.dumps([operation, payload], sort_keys=True).encode()).hexdigest()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT body FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError("Session not found")
            session = json.loads(row[0])
            previous = connection.execute("SELECT fingerprint FROM mutations WHERE session_id=? AND mutation_id=?",
                                          (session_id, mutation_id)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise Conflict("Mutation ID already used for a different request")
                return session
            if session["revision"] != revision:
                raise Conflict("Session changed. Refresh before saving again.")
            apply(session)
            session["revision"] += 1
            session["updated_at"] = now()
            connection.execute("UPDATE sessions SET body=?, updated_at=? WHERE id=?",
                               (json.dumps(session), session["updated_at"], session_id))
            connection.execute("INSERT INTO mutations VALUES (?, ?, ?)", (session_id, mutation_id, fingerprint))
        return session
