import os
import sqlite3
from contextlib import closing
from datetime import datetime

# One local SQLite file holds saved queries, run history, connections and the schema cache.
# sqlite3 ships with Python, so this adds no dependency and keeps data on disk instead of in RAM.
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cloudsql_queries.db')


def connect():
    return closing(sqlite3.connect(DB_FILE))


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def add_column_if_missing(conn, table, column, definition):
    """Small migration helper for databases created by an older version of the app."""
    columns = [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
    if column not in columns:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
