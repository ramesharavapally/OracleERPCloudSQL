import json

from db import connect as _connect, now as _now, add_column_if_missing

HISTORY_LIMIT = 200


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
        add_column_if_missing(conn, 'saved_queries', 'folder', "TEXT DEFAULT ''")
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

def save_query(name, sql_text, tags='', folder=''):
    """Insert a new saved query, or overwrite the one with the same name.
    Returns True when an existing query was updated."""
    now = _now()
    with _connect() as conn, conn:
        exists = conn.execute('SELECT 1 FROM saved_queries WHERE name = ?', (name,)).fetchone()
        if exists:
            conn.execute('UPDATE saved_queries SET sql_text = ?, tags = ?, folder = ?, updated_at = ? WHERE name = ?',
                         (sql_text, tags, folder, now, name))
        else:
            conn.execute("""INSERT INTO saved_queries (name, sql_text, tags, folder, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)""", (name, sql_text, tags, folder, now, now))
    return bool(exists)


def list_queries(search='', folder=None):
    """Return (name, tags, updated_at, folder) rows, filtered on name / tags / SQL text and optionally folder."""
    pattern = f'%{search.strip()}%'
    sql = """SELECT name, tags, updated_at, folder FROM saved_queries
              WHERE (name LIKE ? OR tags LIKE ? OR sql_text LIKE ?)"""
    params = [pattern, pattern, pattern]
    if folder is not None:
        sql += " AND COALESCE(folder, '') = ?"
        params.append(folder)
    with _connect() as conn:
        return conn.execute(sql + ' ORDER BY updated_at DESC', params).fetchall()


def list_folders():
    with _connect() as conn:
        rows = conn.execute("""SELECT DISTINCT COALESCE(folder, '') FROM saved_queries
                                ORDER BY 1""").fetchall()
    return [row[0] for row in rows]


def get_query(name):
    """Return (sql_text, tags, folder), or (None, None, None) when the name does not exist."""
    with _connect() as conn:
        row = conn.execute('SELECT sql_text, tags, folder FROM saved_queries WHERE name = ?', (name,)).fetchone()
    return row if row else (None, None, None)


def delete_query(name):
    with _connect() as conn, conn:
        conn.execute('DELETE FROM saved_queries WHERE name = ?', (name,))


def export_queries_json():
    with _connect() as conn:
        rows = conn.execute("""SELECT name, folder, tags, sql_text FROM saved_queries
                                ORDER BY folder, name""").fetchall()
    queries = [{'name': n, 'folder': f or '', 'tags': t or '', 'sql': s} for n, f, t, s in rows]
    return json.dumps({'saved_queries': queries}, indent=2)


def import_queries_json(text, overwrite=False):
    """Import queries exported by export_queries_json. Returns (added, updated, skipped)."""
    data = json.loads(text)
    queries = data.get('saved_queries') if isinstance(data, dict) else data
    if not isinstance(queries, list):
        raise ValueError('File does not contain a saved_queries list')
    added = updated = skipped = 0
    for item in queries:
        name = str(item.get('name', '')).strip()
        sql_text = str(item.get('sql', '')).strip()
        if not name or not sql_text:
            skipped += 1
            continue
        if get_query(name)[0] is not None and not overwrite:
            skipped += 1
            continue
        if save_query(name, sql_text, str(item.get('tags', '')), str(item.get('folder', ''))):
            updated += 1
        else:
            added += 1
    return added, updated, skipped


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


def get_history_sql(history_id):
    with _connect() as conn:
        row = conn.execute('SELECT sql_text FROM query_history WHERE id = ?', (history_id,)).fetchone()
    return row[0] if row else None
