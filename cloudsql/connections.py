import configparser

from db import connect as _connect, now as _now

# Passwords go to the operating system's credential store (Windows Credential Manager on Windows).
# Only when no credential store is available do they fall back to the local SQLite file.
KEYRING_SERVICE = 'OracleERPCloudSQL'


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


# ---------- Password storage ----------

_keyring_broken = False


def _keyring_call(action, *args):
    """Call keyring.<action>(...). Returns (ok, result). A missing or failing credential store never breaks the app."""
    global _keyring_broken
    if _keyring_broken:
        return False, None
    try:
        import keyring
        return True, getattr(keyring, action)(KEYRING_SERVICE, *args)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        # No backend, nothing to delete, access denied...: fall back for this call
        return False, None
    except BaseException:
        # Some platform backends crash outside the Exception hierarchy; stop trying for this run
        _keyring_broken = True
        return False, None


def _store_password(name, password):
    """Returns True when the password went to the OS credential store."""
    return _keyring_call('set_password', name, password)[0]


def _read_password(name):
    return _keyring_call('get_password', name)[1]


def _forget_password(name):
    _keyring_call('delete_password', name)


# ---------- Connections ----------

def save_connection(name, url, username, password):
    """Create or update a connection. Returns True when the password is in the OS credential store."""
    in_keyring = _store_password(name, password)
    with _connect() as conn, conn:
        conn.execute("""
            INSERT INTO connections (name, url, username, password_fallback, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET url = excluded.url, username = excluded.username,
                   password_fallback = excluded.password_fallback, updated_at = excluded.updated_at""",
                     (name, url.rstrip('/'), username, None if in_keyring else password, _now()))
    return in_keyring


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
    url, username, fallback = row
    password = fallback if fallback is not None else _read_password(name)
    return url, username, password or ''


def password_in_keyring(name):
    with _connect() as conn:
        row = conn.execute('SELECT password_fallback FROM connections WHERE name = ?', (name,)).fetchone()
    return bool(row) and row[0] is None


def delete_connection(name):
    _forget_password(name)
    with _connect() as conn, conn:
        conn.execute('DELETE FROM connections WHERE name = ?', (name,))
        # The schema cache belongs to the connection as well
        for table in ('meta_objects', 'meta_columns', 'meta_status', 'meta_checked'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                conn.execute(f'DELETE FROM {table} WHERE connection = ?', (name,))


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
