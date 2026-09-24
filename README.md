# Cloud SQL for Oracle ERP Cloud

A small TOAD-style SQL workbench for Oracle ERP (Fusion) Cloud. It runs **on your own machine** with Streamlit and sends each `SELECT` to your pod through a BI Publisher report. The app creates that report for you the first time you connect.

> **Read-only by design.** BI Publisher data models only run queries, so `INSERT`/`UPDATE`/`DELETE`, DDL and PL/SQL calls are not possible.

---

## Installation

1. **Python**: install Python 3.10 or newer (tick *Add python.exe to PATH*).
2. **Get the code**: clone this repository or download it as a ZIP and unpack it.
3. **Setup**: run `setup.bat`. It creates `cloudsql_venv` in the same folder and installs `requirements.txt`. Run it again after every update, and once in every new folder (a new ZIP download has no `cloudsql_venv` yet).
4. **Start**: run `CloudConsole.bat`. The app opens at <http://localhost:8501>.

> Always start the app with `CloudConsole.bat`. It uses the Python inside `cloudsql_venv`, which has the right package versions. Running `streamlit run app.py` from a normal command prompt uses your global Python instead, and an older Streamlit there will not work (the app then says which version it found).

---

## Features

### Connections
- Add a pod under **Connection settings** in the sidebar: name, URL (`https://xxxx.fa.ocs.oraclecloud.com`), username and password.
- **Passwords are kept in the Windows Credential Manager**, not in a file. Connections saved by older versions in `config.ini` are moved there automatically on first start.
- **↩ Last query run on …** reopens the last query you ran on that connection.

### SQL editor
| Action | How |
|---|---|
| Run the statement under the cursor | **Ctrl+Enter**. Statements are separated by a blank line or `;` |
| Run only part of the text | Select it, then **Ctrl+Enter** |
| Run everything in the editor | **▶ Run** |
| Autocomplete | Type 2+ letters or press **Ctrl+Space**: SQL keywords, table/view names (after downloading the object list) and columns of tables used in the query |
| Bind variables | Write `:p_org_id`; an input box appears. Numbers go in as-is, text is quoted, empty means `NULL` |
| Row limit | 100 / 1,000 (default) / 10,000 / All. Sent as `FETCH FIRST n ROWS ONLY` |
| Format | **Format** re-indents each statement and upper-cases keywords |
| Several queries at once | **＋ New** opens another query tab, **✕ Close** closes the current one |
| Fallback | **Plain text editor** switches to a simple text box if the highlighting editor ever fails to load |

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
- **💾 Save query** under the editor: name, optional **folder** and tags. Same name overwrites.
- Search by name, tag or SQL text; filter by folder; **Load** into the current tab or **＋Tab** for a new tab.
- **Import / export saved queries** as a JSON file to share with colleagues.
- **Recent runs** keeps your last 200 runs to reopen.

### Compare two connections
**⇄ Compare with another connection** runs the query in the editor on two pods (for example DEV and TEST). It shows the row counts and lists the rows found on only one side.

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
