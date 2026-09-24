import os
import sqlite3
from contextlib import closing
from datetime import datetime

# Local SQLite file that keeps saved queries and run history.
# sqlite3 ships with Python, so this adds no dependency and uses almost no memory.
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cloudsql_queries.db')
HISTORY_LIMIT = 200


def _connect():
    return closing(sqlite3.connect(DB_FILE))


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def init_db():
    with _connect() as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_queries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                sql_text    TEXT NOT NULL,
                tags        TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sql_text    TEXT NOT NULL,
                connection  TEXT DEFAULT '',
                status      TEXT DEFAULT '',
                row_count   INTEGER,
                elapsed_sec REAL,
                ran_at      TEXT NOT NULL
            )""")


# ---------- Saved queries ----------

def save_query(name, sql_text, tags=''):
    """Insert a new saved query, or overwrite the one with the same name.
    Returns True when an existing query was updated."""
    now = _now()
    with _connect() as conn, conn:
        exists = conn.execute('SELECT 1 FROM saved_queries WHERE name = ?', (name,)).fetchone()
        if exists:
            conn.execute('UPDATE saved_queries SET sql_text = ?, tags = ?, updated_at = ? WHERE name = ?',
                         (sql_text, tags, now, name))
        else:
            conn.execute('INSERT INTO saved_queries (name, sql_text, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                         (name, sql_text, tags, now, now))
    return bool(exists)


def list_queries(search=''):
    """Return (name, tags, updated_at) rows, filtered on name / tags / SQL text."""
    pattern = f'%{search.strip()}%'
    with _connect() as conn:
        return conn.execute("""
            SELECT name, tags, updated_at FROM saved_queries
             WHERE name LIKE ? OR tags LIKE ? OR sql_text LIKE ?
             ORDER BY updated_at DESC""", (pattern, pattern, pattern)).fetchall()


def get_query(name):
    with _connect() as conn:
        row = conn.execute('SELECT sql_text, tags FROM saved_queries WHERE name = ?', (name,)).fetchone()
    return row if row else (None, None)


def delete_query(name):
    with _connect() as conn, conn:
        conn.execute('DELETE FROM saved_queries WHERE name = ?', (name,))


# ---------- Run history ----------

def add_history(sql_text, connection, status, row_count=None, elapsed_sec=None):
    with _connect() as conn, conn:
        conn.execute("""
            INSERT INTO query_history (sql_text, connection, status, row_count, elapsed_sec, ran_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (sql_text, connection, status, row_count, elapsed_sec, _now()))
        # Keep only the most recent runs so the file never grows unbounded
        conn.execute("""
            DELETE FROM query_history WHERE id NOT IN
                (SELECT id FROM query_history ORDER BY id DESC LIMIT ?)""", (HISTORY_LIMIT,))


def list_history(limit=50):
    """Return (id, sql_text, connection, status, row_count, elapsed_sec, ran_at) rows, newest first."""
    with _connect() as conn:
        return conn.execute("""
            SELECT id, sql_text, connection, status, row_count, elapsed_sec, ran_at
              FROM query_history ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
