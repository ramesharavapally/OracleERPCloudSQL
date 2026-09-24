# Cloud SQL → TOAD-style Workbench: Roadmap

A plan to grow `cloudsql/` (Streamlit + BI Publisher SOAP) into a TOAD-like SQL tool for Oracle ERP Cloud, with two fixed rules:

1. **It always runs on the local machine.** No server, no cloud hosting. The only network calls go to your Fusion pod.
2. **It stays light on memory.** Only the Python standard library is added where possible (`sqlite3` for local storage), and big result sets are never held more than once.

---

## 1. What is realistic with this architecture

All SQL runs through the BI Publisher report `SampleReport.xdo` (`runReport` → base64 CSV). That decides what a "TOAD" can do here:

| TOAD feature | Possible here? | Notes |
|---|---|---|
| SQL editor, run, grid | ✅ | Already there |
| Saved queries / snippets | ✅ | **Done in Phase 1** (SQLite) |
| Query history | ✅ | **Done in Phase 1** (SQLite, last 200 runs) |
| Export results (CSV/Excel) | ✅ | Phase 2 |
| Schema browser (tables, columns, views) | ✅ | Run `ALL_OBJECTS` / `ALL_TAB_COLUMNS` through the same report |
| Autocomplete for tables and columns | ✅ | Cache the metadata in SQLite, then feed it to a code editor component |
| Multiple editor tabs | ✅ | `st.tabs` + session state |
| Row limit / paging | ✅ | Wrap the query in `FETCH FIRST n ROWS ONLY` |
| Bind variables (`:p_org_id`) | ✅ | Find `:name` tokens, ask for values, substitute them |
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

### Phase 2: Editor and results quality of life

| Item | How | Memory impact |
|---|---|---|
| Syntax-highlighted editor with Ctrl+Enter to run | `streamlit-code-editor` or `streamlit-ace` | Small (one JS component) |
| Row limit selector (100 / 1,000 / 10,000 / all) | Wrap the query: `SELECT * FROM (<sql>) FETCH FIRST :n ROWS ONLY` | **Lowers** memory |
| Export to CSV / Excel | `st.download_button`. Build the file only when clicked (`openpyxl` for xlsx) | Only while exporting |
| Bind variables prompt | Regex `:(\w+)` → a form with one input per variable | None |
| Format SQL button | `sqlparse.format(sql, reindent=True, keyword_case='upper')` | Tiny |
| Result filter box | `df[df.astype(str).apply(lambda c: c.str.contains(q, case=False)).any(axis=1)]` | Temporary copy only |

### Phase 3: Schema browser and autocomplete

1. **Metadata fetch** (per connection, on demand, with a "Refresh" button):
   ```sql
   SELECT owner, object_name, object_type FROM all_objects
    WHERE object_type IN ('TABLE','VIEW','SYNONYM')
   ```
   ```sql
   SELECT owner, table_name, column_name, data_type, column_id
     FROM all_tab_columns WHERE table_name = :t
   ```
2. **Cache in SQLite** (`meta_objects`, `meta_columns` keyed by connection) so the browser opens instantly and does not call the pod again.
3. **Browser UI**: a sidebar search that shows columns for the chosen table. Buttons to *insert `SELECT` with all columns* or *insert table name*.
4. **Autocomplete**: pass cached table and column names to the code editor's completer.
5. Store columns only for tables you actually open, so the cache stays small.

### Phase 4: Workspace features

- **Multiple query tabs** (`st.tabs`), each with its own editor, results and row count.
- **Folders / favourites** for saved queries (add a `folder` column) and export/import of saved queries as a JSON file for sharing.
- **Compare results** of the same query across two connections, e.g. DEV vs TEST (row diff via `pandas.merge(indicator=True)`).
- **Per-connection "last query"** restored when you switch environments.

### Phase 5: Hardening

- **Passwords**: today they sit in plain text in `config.ini`. Move them to the OS credential store with `keyring`, which uses Windows Credential Manager. `config.ini` then keeps only the URL and username.
- **Timeouts and errors**: add `timeout=` to `requests` calls and parse the BIP SOAP fault text into a readable error.
- **Session reuse**: use one `requests.Session` per connection to save repeated TLS handshakes.
- **Code split**: `app.py` (UI) / `bip_client.py` (SOAP) / `querystore.py` (SQLite) / `metadata.py` (schema cache).

---

## 3. Keeping memory low (rules for every phase)

1. **Never use `DataFrame.style` for results.** Use `st.dataframe(df)` directly.
2. **Keep one copy of the result.** Store only the DataFrame in `st.session_state`, not the raw base64 or CSV bytes as well.
3. **Limit rows by default** (Phase 2). Most ad-hoc queries only need the first 1,000 rows.
4. **Create export files on demand**, not on every rerun.
5. **Use SQLite for everything that persists** (queries, history, metadata). It lives on disk, not in RAM.
6. **Avoid `@st.cache_data` on query results.** It keeps extra copies in memory per unique input.
7. **Launch with minimal Streamlit overhead** (optional `cloudsql/.streamlit/config.toml`):
   ```toml
   [server]
   headless = true
   runOnSave = false
   fileWatcherType = "none"

   [browser]
   gatherUsageStats = false
   ```

---

## 4. Running locally (unchanged)

```bat
setup.bat          :: once: creates cloudsql_venv and installs requirements
CloudConsole.bat   :: starts the app at http://localhost:8501
```

Saved queries are kept in `cloudsql\cloudsql_queries.db`. Back up that one file to keep your query library.
