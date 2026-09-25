# Cloud SQL for Oracle ERP Cloud

A small TOAD-style SQL workbench for Oracle ERP (Fusion) Cloud. It runs **on your own machine** with Streamlit and sends each `SELECT` to your pod through a BI Publisher report. The app creates that report for you the first time you connect.

> **Read-only by design.** BI Publisher data models only run queries, so `INSERT`/`UPDATE`/`DELETE`, DDL and PL/SQL calls are not possible.

---

## Installation (uv)

The project uses [uv](https://docs.astral.sh/uv/). `pyproject.toml` lists the packages and `uv.lock` pins their exact versions, so every PC gets the same, tested setup.

1. **Python 3.12**: install it and tick *Add python.exe to PATH*. `.python-version` asks for 3.12; if it is missing, uv can download it.
2. **Get the code**: clone this repository or download it as a ZIP and unpack it.
3. **Setup**: run `setup.bat`. It installs uv (with pip) if needed, then runs `uv sync --locked`, which creates `.venv` in the project folder with the locked packages. Run it again after every update.
4. **Start**: run `CloudConsole.bat`. It runs `uv run --locked streamlit run app.py` inside `cloudsql`, so the app always uses `.venv`. The app opens at <http://localhost:8501>.

The same from a terminal:

```bat
uv sync --locked
cd cloudsql
uv run streamlit run app.py
```

> - Do not start the app with a plain `streamlit run app.py`. That uses your global Python and whatever Streamlit it has. The app checks the version and shows a message if it is older than 1.50.
> - The old `cloudsql_venv` folder from earlier versions is no longer used and can be deleted.
> - Without uv: `pip install -r requirements.txt` in your own virtual environment. `requirements.txt` is exported from `uv.lock` with the same versions.
> - To update packages: `uv lock --upgrade`, test, then commit `uv.lock` and re-export `requirements.txt` with `uv export --no-hashes --no-header --format requirements-txt -o requirements.txt`.

---

## Features

### Connections
- Add a pod under **Connection settings** in the sidebar: name, URL (`https://xxxx.fa.ocs.oraclecloud.com`), username and password.
- **Passwords are kept in the Windows Credential Manager**, not in a file. Connections saved by older versions in `config.ini` are moved there automatically on first start.
- **↩ Last query run on …** reopens the last query you ran on that connection.

### SQL editor
| Action | How |
|---|---|
| Run the statement under the cursor | **Ctrl+Enter** or **▶ Run**. Statements are separated by a blank line or `;` |
| Run only part of the text | Select it, then **Ctrl+Enter** |
| Autocomplete | Type 2+ letters or press **Ctrl+Space**: SQL keywords, table/view names (after downloading the object list) and columns of the tables in your query. Type `alias.` (e.g. `h.` after `FROM doo_headers_all h`) to list only that table's columns. Columns are fetched from the pod once per table, the moment you type the table name, and then kept locally |
| Bind variables | Write `:p_org_id`; a small value box appears next to **▶ Run**. Numbers go in as-is, text is quoted, empty means `NULL` |
| Row limit | Top right: 100 / 1,000 (default) / 10,000 / All rows. Sent as `FETCH FIRST n ROWS ONLY` |
| Format | **Format** (top right) re-indents each statement and upper-cases keywords |
| Several queries at once | **＋ New** opens another query tab, **✕ Close** closes the current one |
| Fallback | If the highlighting editor ever fails to load, add `plain_editor = true` under `[DEFAULT]` in `cloudsql/config.ini` to use a simple text box |

### Results
- Row count and run time, and a notice when the row limit was reached.
- **Filter results**: shows only rows containing the typed text.
- **⬇ CSV / ⬇ Excel** export. The file is built only when you click.
- **SQL sent to the pod** shows the exact SQL after binds and the row limit.
- Errors are short and readable (e.g. `ORA-00942: table or view does not exist`), with full details in an expander.

### Schema browser (🗂 tab)
1. Click **⬇ Download object list** once per connection. The list of tables and views is saved locally.
2. Search by name, pick a table to see its columns (cached after the first look-up).
3. **Insert this SELECT into the editor** writes a `SELECT` with all columns into the current query tab.

### Saved queries (sidebar)
- **💾 Save** (top right, above the editor): name, optional **folder** and tags. Same name overwrites.
- Search by name, tag or SQL text; filter by folder; **Load** into the current tab or **＋Tab** for a new tab.
- **Import / export saved queries** as a JSON file to share with colleagues.
- **Recent runs** keeps your last 200 runs to reopen.

### Compare two connections
**⇄ Compare** (top right, above the editor) runs the query in the editor on two pods (for example DEV and TEST). The result appears under the query results with the row counts and the rows found on only one side.

---

## Where your data is kept

| What | Where |
|---|---|
| Saved queries, run history, connections, schema cache | `cloudsql/cloudsql_queries.db` (SQLite). **Back up this one file.** |
| Passwords | Windows Credential Manager (service `OracleERPCloudSQL`) |
| Autocomplete word lists | `cloudsql/components/sql_editor/cache/` |
| Report paths and optional query timeout | `cloudsql/config.ini` (`[DEFAULT]` section; `query_timeout_seconds`, default 600) |

All of these are ignored by git.

---

## Keeping memory low

- Results are shown in a plain grid (no per-cell HTML styling) and default to 1,000 rows.
- Only one copy of each result is kept; the previous result is freed before a new query runs.
- Export files are created on demand.
- Everything that persists lives in SQLite on disk, not in memory.
- `cloudsql/.streamlit/config.toml` turns off file watching and usage statistics.

See [`docs/TOAD_ROADMAP.md`](docs/TOAD_ROADMAP.md) for the design notes and limits.
