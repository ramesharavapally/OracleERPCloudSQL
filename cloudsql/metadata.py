import json
import os
import re

from db import connect as _connect, now as _now

# Word lists for the editor's autocomplete are written next to the editor component,
# so the browser loads them as a static file instead of receiving them on every rerun.
WORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'components', 'sql_editor', 'cache')

OBJECTS_SQL = """SELECT owner, object_name, object_type
  FROM all_objects
 WHERE object_type IN ('TABLE', 'VIEW')
   AND object_name NOT LIKE 'BIN$%'
   AND owner IN (SELECT username FROM all_users WHERE oracle_maintained = 'N')"""

COLUMNS_SQL = """SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, column_id
  FROM all_tab_columns
 WHERE owner = {owner} AND table_name = {table}
 ORDER BY column_id"""

# Columns of several tables in one round trip (used for the editor autocomplete)
COLUMNS_BATCH_SQL = """SELECT owner, table_name, column_name, data_type, data_length, data_precision, data_scale,
       nullable, column_id
  FROM all_tab_columns
 WHERE table_name IN ({tables})
   AND owner IN (SELECT username FROM all_users WHERE oracle_maintained = 'N')
 ORDER BY owner, table_name, column_id"""

# Table names written after FROM / JOIN, optionally with an owner prefix (FROM fusion.po_headers_all h)
_FROM_JOIN = re.compile(r'\b(?:FROM|JOIN)\s+(?:[A-Za-z_][\w$#]*\.)?([A-Za-z_][\w$#]*)', re.IGNORECASE)
_IDENTIFIER = re.compile(r'[A-Za-z_][\w$#]*')


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def init_db():
    with _connect() as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_objects (
                connection  TEXT NOT NULL,
                owner       TEXT NOT NULL,
                object_name TEXT NOT NULL,
                object_type TEXT NOT NULL
            )""")
        conn.execute('CREATE INDEX IF NOT EXISTS meta_objects_ix ON meta_objects (connection, object_name)')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_columns (
                connection  TEXT NOT NULL,
                owner       TEXT NOT NULL,
                table_name  TEXT NOT NULL,
                column_name TEXT NOT NULL,
                data_type   TEXT,
                nullable    TEXT,
                column_id   INTEGER
            )""")
        conn.execute('CREATE INDEX IF NOT EXISTS meta_columns_ix ON meta_columns (connection, table_name)')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_status (
                connection   TEXT PRIMARY KEY,
                object_count INTEGER,
                loaded_at    TEXT
            )""")
        # Tables whose columns were already looked up for autocomplete (also those that do not exist)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_checked (
                connection TEXT NOT NULL,
                table_name TEXT NOT NULL,
                PRIMARY KEY (connection, table_name)
            )""")


def _words_file(connection):
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', connection)
    return os.path.join(WORDS_DIR, f'{safe}.json')


def words_url(connection):
    """Path of the autocomplete word list, relative to the editor component, or None if not downloaded."""
    status = object_status(connection)
    if not status or not os.path.exists(_words_file(connection)):
        return None
    return f'cache/{os.path.basename(_words_file(connection))}?v={status[1].replace(" ", "_")}'


def refresh_objects(connection, run_sql):
    """Download all table and view names for a connection into the local cache.
    run_sql(sql) must return a DataFrame. Returns the number of objects."""
    df = run_sql(OBJECTS_SQL)
    df.columns = [c.upper() for c in df.columns]
    rows = list(df[['OWNER', 'OBJECT_NAME', 'OBJECT_TYPE']].itertuples(index=False, name=None))
    names = sorted(set(df['OBJECT_NAME'].astype(str)))
    del df
    with _connect() as conn, conn:
        conn.execute('DELETE FROM meta_objects WHERE connection = ?', (connection,))
        # Tables that did not exist before are looked up again after a refresh
        conn.execute('DELETE FROM meta_checked WHERE connection = ?', (connection,))
        conn.executemany('INSERT INTO meta_objects VALUES (?, ?, ?, ?)',
                         [(connection, *row) for row in rows])
        conn.execute("""INSERT INTO meta_status VALUES (?, ?, ?)
                        ON CONFLICT(connection) DO UPDATE SET object_count = excluded.object_count,
                               loaded_at = excluded.loaded_at""", (connection, len(rows), _now()))
    os.makedirs(WORDS_DIR, exist_ok=True)
    with open(_words_file(connection), 'w') as f:
        json.dump(names, f)
    return len(rows)


def forget(connection):
    """Remove the autocomplete word list of a deleted connection (its cache rows go with the connection)."""
    try:
        os.remove(_words_file(connection))
    except OSError:
        pass


def object_status(connection):
    """Return (object_count, loaded_at) or None when the list was never downloaded."""
    with _connect() as conn:
        return conn.execute('SELECT object_count, loaded_at FROM meta_status WHERE connection = ?',
                            (connection,)).fetchone()


def search_objects(connection, text, limit=200):
    """Return (owner, object_name, object_type) rows whose name contains text. Names starting with it come first."""
    text = text.strip().upper()
    with _connect() as conn:
        return conn.execute("""
            SELECT owner, object_name, object_type FROM meta_objects
             WHERE connection = ? AND object_name LIKE ?
             ORDER BY CASE WHEN object_name LIKE ? THEN 0 ELSE 1 END, object_name
             LIMIT ?""", (connection, f'%{text}%', f'{text}%', limit)).fetchall()


def get_columns(connection, owner, table, run_sql, refresh=False):
    """Return (column_name, data_type, nullable, column_id) rows, from the cache or fetched from the pod."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT column_name, data_type, nullable, column_id FROM meta_columns
             WHERE connection = ? AND owner = ? AND table_name = ? ORDER BY column_id""",
                            (connection, owner, table)).fetchall()
    if rows and not refresh:
        return rows

    df = run_sql(COLUMNS_SQL.format(owner=_quote(owner), table=_quote(table)))
    df.columns = [c.upper() for c in df.columns]
    rows = [_column_row(r) for r in df.itertuples(index=False)]
    with _connect() as conn, conn:
        conn.execute('DELETE FROM meta_columns WHERE connection = ? AND owner = ? AND table_name = ?',
                     (connection, owner, table))
        conn.executemany('INSERT INTO meta_columns VALUES (?, ?, ?, ?, ?, ?, ?)',
                         [(connection, owner, table, *row) for row in rows])
    return rows


def _column_row(r):
    """(column_name, data_type, nullable, column_id) from one ALL_TAB_COLUMNS row, e.g. VARCHAR2(30), NUMBER(18)."""
    data_type = str(r.DATA_TYPE)
    if data_type in ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'RAW') and r.DATA_LENGTH == r.DATA_LENGTH:
        data_type += f'({int(r.DATA_LENGTH)})'
    elif data_type == 'NUMBER' and r.DATA_PRECISION == r.DATA_PRECISION:  # x == x is False for NaN
        scale = int(r.DATA_SCALE) if r.DATA_SCALE == r.DATA_SCALE else 0
        data_type += f'({int(r.DATA_PRECISION)}{"," + str(scale) if scale else ""})'
    return str(r.COLUMN_NAME), data_type, str(r.NULLABLE), int(r.COLUMN_ID)


def tables_in_sql(connection, sql_text):
    """Upper-case names of tables the SQL uses: words after FROM/JOIN, plus any word that is a known
    table or view in the downloaded object list (catches comma joins like FROM a x, b y)."""
    names = {m.upper() for m in _FROM_JOIN.findall(sql_text or '')}
    words = list({w.upper() for w in _IDENTIFIER.findall(sql_text or '')})[:500]
    if words:
        with _connect() as conn:
            names.update(row[0] for row in conn.execute(
                f"""SELECT DISTINCT object_name FROM meta_objects
                     WHERE connection = ? AND object_name IN ({','.join('?' * len(words))})""",
                (connection, *words)))
    return names


def tables_missing_columns(connection, sql_text, limit=10):
    """Tables used in the SQL whose columns were never looked up (at most `limit`, sorted)."""
    names = tables_in_sql(connection, sql_text)
    if not names:
        return []
    marks = ','.join('?' * len(names))
    with _connect() as conn:
        known = {row[0] for row in conn.execute(
            f"""SELECT table_name FROM meta_checked WHERE connection = ? AND table_name IN ({marks})
                UNION SELECT table_name FROM meta_columns WHERE connection = ? AND table_name IN ({marks})""",
            (connection, *names, connection, *names))}
    return sorted(names - known)[:limit]


def fetch_columns(connection, tables, run_sql):
    """Look up the columns of several tables in one query and cache them. Tables that do not exist
    are remembered too, so they are not asked for again."""
    if not tables:
        return
    df = run_sql(COLUMNS_BATCH_SQL.format(tables=', '.join(_quote(t) for t in tables)))
    df.columns = [c.upper() for c in df.columns]
    rows = [(str(r.OWNER), str(r.TABLE_NAME), *_column_row(r)) for r in df.itertuples(index=False)]
    del df
    with _connect() as conn, conn:
        for owner, table in {(r[0], r[1]) for r in rows}:
            conn.execute('DELETE FROM meta_columns WHERE connection = ? AND owner = ? AND table_name = ?',
                         (connection, owner, table))
        conn.executemany('INSERT INTO meta_columns VALUES (?, ?, ?, ?, ?, ?, ?)',
                         [(connection, *row) for row in rows])
        conn.executemany('INSERT OR IGNORE INTO meta_checked VALUES (?, ?)', [(connection, t) for t in tables])


def known_columns(connection, sql_text, limit_tables=20):
    """Column names of cached tables that appear in the SQL, for autocomplete. Returns [(column, table)]."""
    # SQLite limits the number of ? parameters, and table names are never that many in one query
    words = list({w.upper() for w in re.findall(r'[A-Za-z_][\w$#]*', sql_text or '')})[:500]
    if not words:
        return []
    with _connect() as conn:
        tables = [row[0] for row in conn.execute(
            f"""SELECT DISTINCT table_name FROM meta_columns
                 WHERE connection = ? AND table_name IN ({','.join('?' * len(words))})""",
            (connection, *words)).fetchall()][:limit_tables]
        if not tables:
            return []
        return conn.execute(
            f"""SELECT DISTINCT column_name, table_name FROM meta_columns
                 WHERE connection = ? AND table_name IN ({','.join('?' * len(tables))})""",
            (connection, *tables)).fetchall()


def select_statement(owner, table, columns):
    column_list = ',\n       '.join(c[0] for c in columns) if columns else '*'
    # Fusion application tables are reachable without the owner prefix; other schemas need it
    source = table if owner == 'FUSION' else f'{owner}.{table}'
    return f'SELECT {column_list}\n  FROM {source}'
