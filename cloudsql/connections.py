import configparser
import json

from db import connect as _connect, now as _now


def init_db():
    with _connect() as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                name              TEXT PRIMARY KEY,
                url               TEXT NOT NULL,
                username          TEXT NOT NULL,
                password_fallback TEXT,
                last_sql          TEXT,
                updated_at        TEXT NOT NULL
            )""")
        # Older versions kept passwords in the Windows Credential Manager; move them into the table once
        for (name,) in conn.execute('SELECT name FROM connections WHERE password_fallback IS NULL').fetchall():
            password = _legacy_keyring_password(name)
            if password:
                conn.execute('UPDATE connections SET password_fallback = ? WHERE name = ?', (password, name))


# The password column is still called password_fallback so databases created by older versions keep working.

def _legacy_keyring_password(name):
    try:
        import keyring
        return keyring.get_password('OracleERPCloudSQL', name)
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return None


# ---------- Connections ----------

def save_connection(name, url, username, password):
    """Create or update a connection, including its username and password."""
    with _connect() as conn, conn:
        conn.execute("""
            INSERT INTO connections (name, url, username, password_fallback, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET url = excluded.url, username = excluded.username,
                   password_fallback = excluded.password_fallback, updated_at = excluded.updated_at""",
                     (name, url.rstrip('/'), username, password, _now()))


def list_connections():
    with _connect() as conn:
        return [row[0] for row in conn.execute('SELECT name FROM connections ORDER BY name')]


def get_connection(name):
    """Return (url, username, password), or ('', '', '') when the connection does not exist."""
    with _connect() as conn:
        row = conn.execute('SELECT url, username, password_fallback FROM connections WHERE name = ?',
                           (name,)).fetchone()
    if not row:
        return '', '', ''
    url, username, password = row
    return url, username, password or ''


def delete_connection(name):
    with _connect() as conn, conn:
        conn.execute('DELETE FROM connections WHERE name = ?', (name,))
        # The schema cache belongs to the connection as well
        for table in ('meta_objects', 'meta_columns', 'meta_status', 'meta_checked'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                conn.execute(f'DELETE FROM {table} WHERE connection = ?', (name,))


def export_connections_json():
    """All connections as JSON, passwords included in plain text, so keep the file private."""
    with _connect() as conn:
        rows = conn.execute('SELECT name, url, username, password_fallback FROM connections ORDER BY name').fetchall()
    return json.dumps({'connections': [{'name': n, 'url': u, 'username': user, 'password': pw or ''}
                                       for n, u, user, pw in rows]}, indent=2)


def import_connections_json(text, overwrite=False):
    """Returns (added, updated, skipped)."""
    data = json.loads(text)
    items = data.get('connections') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError('not a connections export file')
    existing = set(list_connections())
    added = updated = skipped = 0
    for item in items:
        name, url, user = (str(item.get(k) or '').strip() for k in ('name', 'url', 'username'))
        if not (name and url and user):
            skipped += 1
        elif name in existing and not overwrite:
            skipped += 1
        else:
            save_connection(name, url, user, str(item.get('password') or ''))
            if name in existing:
                updated += 1
            else:
                added += 1
                existing.add(name)
    return added, updated, skipped


def set_last_sql(name, sql_text):
    with _connect() as conn, conn:
        conn.execute('UPDATE connections SET last_sql = ? WHERE name = ?', (sql_text, name))


def get_last_sql(name):
    with _connect() as conn:
        row = conn.execute('SELECT last_sql FROM connections WHERE name = ?', (name,)).fetchone()
    return row[0] if row and row[0] else ''


def migrate_from_config(config_file):
    """Move connections that older versions kept in config.ini (password in plain text) into this store.
    config.ini keeps only its [DEFAULT] settings afterwards. Returns the migrated connection names."""
    config = configparser.ConfigParser()
    config.read(config_file)
    sections = config.sections()
    if not sections:
        return []
    existing = set(list_connections())
    for name in sections:
        section = config[name]
        if name not in existing and section.get('url'):
            save_connection(name, section.get('url', ''), section.get('username', ''), section.get('password', ''))
    for name in sections:
        config.remove_section(name)
    with open(config_file, 'w') as configfile:
        config.write(configfile)
    return sections
