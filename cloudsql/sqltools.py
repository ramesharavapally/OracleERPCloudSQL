import re

# Matches, in order: 'string literals', "quoted identifiers", -- line comments, /* block comments */
_SKIP_PATTERN = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|--[^\n]*|/\*.*?\*/", re.DOTALL)
_BIND_PATTERN = re.compile(r'(?<![\w:]):([A-Za-z_][\w$#]*)')
_NUMBER_PATTERN = re.compile(r'-?\d+(\.\d+)?')


def _split_code(sql):
    """Yield (is_code, text) chunks so binds are never touched inside literals or comments."""
    pos = 0
    for match in _SKIP_PATTERN.finditer(sql):
        if match.start() > pos:
            yield True, sql[pos:match.start()]
        yield False, match.group(0)
        pos = match.end()
    if pos < len(sql):
        yield True, sql[pos:]


def clean_sql(sql):
    """Trim whitespace and trailing ';' or '/' that BI Publisher rejects."""
    sql = sql.strip()
    while sql and sql[-1] in ';/':
        sql = sql[:-1].rstrip()
    return sql


def find_binds(sql):
    """Return bind variable names (e.g. p_org_id for :p_org_id) in order of first use, case-insensitive."""
    names = {}
    for is_code, chunk in _split_code(sql):
        if is_code:
            for name in _BIND_PATTERN.findall(chunk):
                names.setdefault(name.upper(), name)
    return list(names.values())


def to_literal(value):
    """Numbers go in as-is, everything else as a quoted string. An empty value becomes NULL."""
    value = value.strip()
    if value == '':
        return 'NULL'
    if _NUMBER_PATTERN.fullmatch(value):
        return value
    return "'" + value.replace("'", "''") + "'"


def apply_binds(sql, values):
    """Replace :name with the literal for values[name] (matched case-insensitively)."""
    literals = {name.upper(): to_literal(value) for name, value in values.items()}

    def replace(match):
        return literals.get(match.group(1).upper(), match.group(0))

    return ''.join(_BIND_PATTERN.sub(replace, chunk) if is_code else chunk
                   for is_code, chunk in _split_code(sql))


def apply_row_limit(sql, limit):
    """Wrap the query so the pod only sends back the first `limit` rows. None means no limit."""
    if not limit:
        return sql
    return f'SELECT * FROM (\n{sql}\n) FETCH FIRST {int(limit)} ROWS ONLY'


def format_sql(sql):
    """Format each statement (blocks separated by blank lines) on its own, keeping the blank lines."""
    import sqlparse  # imported only when the Format button is used
    blocks = [b for b in re.split(r'\n[ \t]*\n', sql) if b.strip()]
    return '\n\n'.join(sqlparse.format(b.strip(), reindent=True, keyword_case='upper') for b in blocks)
