# Cloud SQL → TOAD-style Workbench: Roadmap (all phases done)

A plan to grow `cloudsql/` (Streamlit + BI Publisher SOAP) into a TOAD-like SQL tool for Oracle ERP Cloud, with two fixed rules:

1. **It always runs on the local machine.** No server, no cloud hosting. The only network calls go to your Fusion pod.
2. **It stays light on memory.** Only the Python standard library is added where possible (`sqlite3` for local storage), and big result sets are never held more than once.

---

## 1. What is realistic with this architecture

All SQL runs through the BI Publisher report `SampleReport.xdo` (`runReport` → base64 CSV). That decides what a "TOAD" can do here:

| TOAD feature | Possible here? | Notes |
|---|---|---|
| SQL editor, run, grid | ✅ | Highlighting editor with Ctrl+Enter added in Phase 3 |
| Saved queries / snippets | ✅ | **Done in Phase 1** (SQLite) |
| Query history | ✅ | **Done in Phase 1** (SQLite, last 200 runs) |
| Export results (CSV/Excel) | ✅ | **Done in Phase 2** |
| Schema browser (tables, columns, views) | ✅ | **Done in Phase 3** |
| Autocomplete for tables and columns | ✅ | **Done in Phase 3** (own Ace-based editor component) |
| Multiple editor tabs | ✅ | **Done in Phase 4** |
| Row limit / paging | ✅ | **Done in Phase 2** (`FETCH FIRST n ROWS ONLY`) |
| Bind variables (`:p_org_id`) | ✅ | **Done in Phase 2** |
| Explain plan | ⚠️ Limited | BIP data models only run `SELECT`. No `EXPLAIN PLAN` or `DBMS_XPLAN` |
| DML / DDL / PL/SQL execution | ❌ | Not possible through BIP. This stays a read-only tool |
| Session browser, locks, debugger | ❌ | Needs a direct DB connection, which ERP Cloud does not give |

---

## 2. Phases

### ✅ Phase 1: Saved queries, history, lighter grid (done)

- `cloudsql/querystore.py`: a small SQLite layer. The database is `cloudsql/cloudsql_queries.db`, created on first run and git-ignored.
  - `saved_queries(name UNIQUE, sql_text, tags, created_at, updated_at)`
  - `query_history(sql_text, connection, status, row_count, elapsed_sec, ran_at)`, trimmed automatically to 200 rows
- Main page, **💾 Save query**: enter a name and optional tags. Saving under an existing name overwrites that query.
- Sidebar, **Saved Queries**: search by name, tag or SQL text, preview the query, then **Load** it into the editor or **Delete** it.
- Sidebar, **Recent runs**: reload any earlier query into the editor.
- A `rows in seconds` line under each result.
- **Memory fix:** results used to be rendered through a pandas `Styler`, with `styler.render.max_elements = 50,000,000`. That turns every cell into HTML and was the largest memory cost in the app. A plain `st.dataframe` now renders the grid instead.

### ✅ Phase 2: Editor and results quality of life (done)

| Item | How it works | Memory impact |
|---|---|---|
| **Row limit** (100 / 1,000 / 10,000 / All, default 1,000) | The query is sent as `SELECT * FROM (<sql>) FETCH FIRST n ROWS ONLY`. A note appears when the limit is reached | **Lowers** memory |
| **Bind variables** | Each `:name` in the SQL gets an input box. Numbers are sent as-is, other text is quoted, empty means `NULL`. `:x` inside strings, comments and `"quoted"` names is ignored | None |
| **Format** button | `sqlparse` re-indents and upper-cases keywords | Tiny |
| **Result filter** | Shows only rows that contain the typed text in any column | Temporary copy only while filtering |
| **Export CSV / Excel** | The file is built only when you click the button (needs Streamlit 1.52+) | Only while exporting |
| **SQL sent to the pod** | An expander shows the exact SQL after binds and the row limit were applied | None |
| Trailing `;` or `/` | Removed automatically before sending | None |

History and saved queries keep your **original** SQL (with `:binds`), so reloaded queries stay reusable.

> The highlighting editor was moved to Phase 3: the ready-made components (`streamlit-ace`, `streamlit-code-editor`) cannot take new text from outside once on screen and cannot autocomplete your own table names, so the app now ships its own small editor component.

### ✅ Phase 3: Schema browser, highlighting editor, autocomplete (done)

- **`metadata.py`**: downloads table and view names once per connection from `ALL_OBJECTS` (application schemas only: `ALL_USERS.ORACLE_MAINTAINED = 'N'`) into the SQLite tables `meta_objects` / `meta_status`. Columns come from `ALL_TAB_COLUMNS`, fetched only for tables you open and cached in `meta_columns`.
- **🗂 Schema browser tab**: instant local search, column list with types, and **Insert this SELECT into the editor**.
- **Editor component** (`components/sql_editor/`): the Ace editor (BSD licence, stored in the repo so it works offline) wired to Streamlit with plain HTML/JS, with no npm build step.
  - **Ctrl+Enter** runs the statement under the cursor (blank line or `;` separates statements) or the selected text. **▶ Run** runs everything.
  - Autocomplete: SQL keywords, table and view names (loaded by the browser from a static JSON file, so the list is never re-sent on every rerun), and columns of cached tables used in the query.
  - **Plain text editor** toggle as a fallback.

### ✅ Phase 4: Workspace features (done)

- **Query tabs**: **＋ New** / **✕ Close**, one button per tab. Each tab keeps its own SQL, result and error. Buttons are used instead of a radio so renaming a tab (e.g. when saving) cannot confuse the selection.
- **Folders** for saved queries (a new `folder` column, added automatically to existing databases) and a folder filter in the sidebar.
- **Import / export** of saved queries as JSON, with an option to overwrite queries that have the same name.
- **Compare** (`compare.py`): runs the same SQL on two connections and matches rows one to one on the common columns. `1` and `1.0` count as equal, and duplicates are respected.
- **Last query per connection**: a sidebar button reopens the last query run on the selected connection.

### ✅ Phase 5: Hardening (done)

- **Passwords** are kept in the Windows Credential Manager via `keyring`. Connections moved from `config.ini` to SQLite, and `config.ini` now only holds `[DEFAULT]` settings. Old `config.ini` connections are migrated automatically. If no credential store is available, the password falls back to the local database file and the sidebar says so.
- **`bip_client.py`**: one shared `requests.Session`, a connect timeout (15 s), a read timeout (`query_timeout_seconds`, default 600 s), and readable errors (`ORA-xxxxx` line, HTTP 401/403/404, last Java exception message). Full details stay available in an expander.
- **Code split**: `app.py` (UI), `bip_client.py` (SOAP), `reportutils.py` (report creation), `connections.py`, `querystore.py`, `metadata.py`, `sqltools.py`, `compare.py`, `db.py` (shared SQLite helper).

---

## 3. Keeping memory low (rules for every phase)

1. **Never use `DataFrame.style` for results.** Use `st.dataframe(df)` directly.
2. **Keep one copy of the result.** Store only the DataFrame in `st.session_state`, not the raw base64 or CSV bytes as well.
3. **Limit rows by default** (done: 1,000 rows unless you pick more). Most ad-hoc queries only need the first 1,000 rows.
4. **Create export files on demand**, not on every rerun.
5. **Use SQLite for everything that persists** (queries, history, metadata). It lives on disk, not in RAM.
6. **Avoid `@st.cache_data` on query results.** It keeps extra copies in memory per unique input.
7. **Launch with minimal Streamlit overhead** (done in `cloudsql/.streamlit/config.toml`): no file watcher, no usage statistics, minimal toolbar.
8. **Keep big lists out of reruns.** The autocomplete word list is a static file the browser loads once, not a component argument.

---

## 4. Running locally

```bat
setup.bat          :: once: creates cloudsql_venv and installs requirements
CloudConsole.bat   :: starts the app at http://localhost:8501
```

Saved queries, history, connections and the schema cache are kept in `cloudsql\cloudsql_queries.db`. Back up that one file to keep your query library.
