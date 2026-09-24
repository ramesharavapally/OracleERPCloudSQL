import configparser
import os
import time
from io import BytesIO

import pandas as pd
import streamlit as st
from packaging.version import Version

import bip_client
import connections
import metadata
import querystore
import sqltools
from bip_client import BipError
from compare import compare_frames
from components.sql_editor import sql_editor
from reportutils import create_report

# Set page configuration to wide mode by default
st.set_page_config(layout="wide" ,
                   page_title="Cloud SQL",
                   page_icon="🌊",)

# Oldest Streamlit the app is tested with. Explain the fix instead of crashing on a missing feature.
MIN_STREAMLIT = '1.50'
if Version(st.__version__) < Version(MIN_STREAMLIT):
    st.error(f'This app needs Streamlit {MIN_STREAMLIT} or newer, but it is running with Streamlit {st.__version__}.')
    st.markdown('Close this window and start the app with **CloudConsole.bat**. If it still appears, '
                'run **setup.bat** once more; it installs the right versions with uv.')
    st.stop()
# Streamlit 1.52+ builds a download file only when its button is clicked
LAZY_DOWNLOADS = Version(st.__version__) >= Version('1.52')
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
ROW_LIMITS = [100, 1000, 10000, 'All']
EDITOR_HEIGHT = 250

ss = st.session_state


def set_css_style():
    st.markdown(
        """
        <style>
        /* Define custom font size and family */
        textarea {
            color: rgb(0, 0, 139) !important;
            font-size: 14px !important;
            font-family: "Source Code Pro", monospace !important;
            font-optical-sizing: auto !important;
        }
        /* Keep the Run row tight under the editor */
        .st-key-run_row { margin-top: -0.75rem; }
        </style>
        """,
        unsafe_allow_html=True
    )


# ---------- Settings from config.ini (report paths, timeout) ----------

def _config_default(key, fallback):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config['DEFAULT'].get(key, fallback)

def get_report_name():
    return _config_default('report_path', '/Custom/py_sql/SampleReport.xdo')

def get_datamodel_name():
    return _config_default('datamodel_path', '/Custom/py_sql/SampleReport.xdm')

def use_plain_editor():
    """Hidden fallback: plain_editor = true in config.ini [DEFAULT] swaps the highlighting editor for a text box."""
    return _config_default('plain_editor', 'false').strip().lower() in ('1', 'true', 'yes')

def get_timeout():
    return (15, int(_config_default('query_timeout_seconds', '600')))


# ---------- Messages that survive a rerun ----------

def flash(level, message):
    ss.setdefault('flashes', []).append((level, message))

def show_flashes():
    for level, message in ss.pop('flashes', []):
        getattr(st, level)(message)

def show_error(message, detail=''):
    st.error(message)
    if detail and detail != message:
        with st.expander('Error details'):
            st.code(detail[:20000])


# ---------- Query tabs ----------

def new_tab_state(tab_id, title=None):
    return {'title': title or f'Query {tab_id}', 'sql': '', 'version': 0, 'df': None, 'info': {}, 'error': None}

def init_tabs():
    if 'qtabs' not in ss:
        ss.qtabs = {1: new_tab_state(1)}
        ss.tab_order = [1]
        ss.active_tab = 1
        ss.next_tab = 2

def active_tab():
    return ss.qtabs[ss.active_tab]

def current_sql(plain=None):
    """Text currently in the editor of the active tab."""
    tab = active_tab()
    plain = ss.get('plain_editor', False) if plain is None else plain
    if plain:
        return ss.get('sql_editor', tab['sql'])
    value = ss.get('ace_editor')
    if value and value.get('version') == tab['version'] and value.get('tab') == ss.active_tab:
        return value.get('text', '')
    return tab['sql']

def set_editor_text(text, title=None):
    """Put new text in the active tab's editor. Only call from widget callbacks."""
    tab = active_tab()
    tab['sql'] = text
    tab['version'] += 1
    ss.sql_editor = text
    if title:
        tab['title'] = title

def show_tab(tab_id):
    ss.active_tab = tab_id
    tab = active_tab()
    ss.sql_editor = tab['sql']
    ss.save_name = tab.get('saved_name', '')

def switch_tab(tab_id):
    if tab_id != ss.active_tab:
        active_tab()['sql'] = current_sql()
        show_tab(tab_id)

def add_tab():
    active_tab()['sql'] = current_sql()
    tab_id = ss.next_tab
    ss.next_tab += 1
    ss.qtabs[tab_id] = new_tab_state(tab_id)
    ss.tab_order.append(tab_id)
    show_tab(tab_id)

def close_tab():
    if len(ss.tab_order) == 1:
        tab_id = ss.active_tab
        ss.qtabs[tab_id] = new_tab_state(tab_id, 'Query 1')
        ss.qtabs[tab_id]['version'] = 1
        show_tab(tab_id)
        return
    index = ss.tab_order.index(ss.active_tab)
    ss.tab_order.remove(ss.active_tab)
    del ss.qtabs[ss.active_tab]
    show_tab(ss.tab_order[min(index, len(ss.tab_order) - 1)])

# ---------- Editor callbacks ----------

def format_editor_sql():
    try:
        set_editor_text(sqltools.format_sql(current_sql()))
    except ImportError:
        flash('warning', 'Formatting needs the sqlparse package: run setup.bat again')

def bind_inputs(sql_text):
    """One small input per :bind variable, shown next to the Run button. Returns {name: value}."""
    for name in sqltools.find_binds(sql_text):
        st.markdown(f'`:{name}`', width='content')
        st.text_input(f':{name}', key=f'bind_{name.upper()}', width=160, label_visibility='collapsed',
                      placeholder='value', help='Numbers are sent as-is, other text is quoted, empty means NULL')
    return {name: ss.get(f'bind_{name.upper()}', '') for name in sqltools.find_binds(sql_text)}

def prepare_sql(text, bind_values, row_limit):
    return sqltools.apply_row_limit(sqltools.apply_binds(sqltools.clean_sql(text), bind_values), row_limit)


# ---------- Saved queries / history callbacks ----------

def load_saved_query():
    sql_text, tags, folder = querystore.get_query(ss.sq_pick)
    if sql_text is not None:
        set_editor_text(sql_text, title=ss.sq_pick)
        active_tab()['saved_name'] = ss.sq_pick
        ss.save_name = ss.sq_pick
        ss.save_tags = tags or ''
        ss.save_folder = folder or ''

def load_saved_query_new_tab():
    add_tab()
    load_saved_query()

def delete_saved_query():
    querystore.delete_query(ss.sq_pick)
    flash('success', f"Deleted saved query '{ss.sq_pick}'")

def save_current_query():
    name = ss.get('save_name', '').strip()
    sql_text = current_sql().strip()
    if not name or not sql_text:
        flash('warning', 'Enter a query name and some SQL before saving')
        return
    updated = querystore.save_query(name, sql_text, ss.get('save_tags', '').strip(), ss.get('save_folder', '').strip())
    tab = active_tab()
    tab['title'] = name
    tab['saved_name'] = name
    flash('success', f"{'Updated' if updated else 'Saved'} query '{name}'")

def load_history_query():
    sql_text = querystore.get_history_sql(ss.get('hist_pick'))
    if sql_text is not None:
        set_editor_text(sql_text)

def load_last_query(connection_name):
    set_editor_text(connections.get_last_sql(connection_name))

def import_queries():
    uploaded = ss.get('import_file')
    if uploaded is None:
        flash('warning', 'Choose a JSON file to import first')
        return
    try:
        added, updated, skipped = querystore.import_queries_json(uploaded.getvalue().decode('utf-8'),
                                                                 overwrite=ss.get('import_overwrite', False))
        flash('success', f'Imported: {added} new, {updated} overwritten, {skipped} skipped')
    except Exception as e:
        flash('error', f'Could not import the file: {e}')


# ---------- Connections ----------

def save_connection_clicked(key):
    name = ss.get(f'conn_name_{key}', '').strip()
    url = ss.get(f'conn_url_{key}', '').strip()
    username = ss.get(f'conn_user_{key}', '').strip()
    password = ss.get(f'conn_pw_{key}', '')
    if not (name and url and username and password):
        flash('warning', 'Fill in connection name, URL, username and password')
        return
    in_keyring = connections.save_connection(name, url, username, password)
    flash('success', f'Saved connection {name}')
    if not in_keyring:
        flash('warning', 'No credential store was available, so the password is kept in the local database file')
    try:
        create_report(url.rstrip('/'), username, password, get_datamodel_name(), get_report_name())
    except Exception as e:
        flash('error', f'Connection saved, but the report could not be created: {e}')
    ss.conn_pick = name
    ss.selected_connection = name

def delete_connection_clicked(name):
    connections.delete_connection(name)
    metadata.forget(name)
    ss.selected_connection = ''
    ss.pop('conn_pick', None)
    flash('success', f'Deleted connection {name}')

def connection_sidebar():
    """Returns (connection_name, url, username, password) of the connection to use."""
    saved = connections.list_connections()
    if ss.get('conn_pick') not in saved:
        ss.pop('conn_pick', None)
    selected = st.sidebar.selectbox('Select Connection:', saved, key='conn_pick')
    url, username, password = connections.get_connection(selected) if selected else ('', '', '')

    ss.setdefault('selected_connection', '')
    if selected and selected != ss.selected_connection:
        try:
            create_report(url, username, password, get_datamodel_name(), get_report_name())
        except Exception as e:
            st.sidebar.error(f'Could not check or create the report on {selected}: {e}')
        ss.selected_connection = selected

    with st.sidebar.expander('Connection settings', expanded=not saved):
        key = selected or 'new'
        name = st.text_input('Connection Name', value=selected or '', key=f'conn_name_{key}')
        url = st.text_input('API URL', value=url, key=f'conn_url_{key}', placeholder='https://xxxx.fa.ocs.oraclecloud.com')
        username = st.text_input('Username', value=username, key=f'conn_user_{key}')
        password = st.text_input('Password', type='password', value=password, key=f'conn_pw_{key}')
        st.button('Save', on_click=save_connection_clicked, args=(key,), width='stretch')
        if selected:
            if connections.password_in_keyring(selected):
                st.caption('🔒 Password is kept in the Windows Credential Manager')
            else:
                st.caption('⚠ Password is kept in the local database file (no credential store available)')
            confirm = st.checkbox(f'Yes, delete {selected}', key=f'confirm_delete_{selected}')
            st.button('Delete connection', on_click=delete_connection_clicked, args=(selected,),
                      disabled=not confirm, width='stretch')

    if selected and connections.get_last_sql(selected):
        st.sidebar.button(f'↩ Last query run on {selected}', on_click=load_last_query, args=(selected,),
                          width='stretch')
    return (name.strip() if name else ''), url.strip().rstrip('/'), username.strip(), password


# ---------- Sidebar: saved queries and history ----------

def saved_queries_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader('Saved Queries')
    folders = querystore.list_folders()
    folder_filter = None
    if len(folders) > 1 or (folders and folders[0]):
        choice = st.sidebar.selectbox('Folder', ['All folders'] + folders, key='sq_folder',
                                      format_func=lambda f: f or '(no folder)')
        folder_filter = None if choice == 'All folders' else choice
    search = st.sidebar.text_input('Search name / tag / SQL', key='sq_search')
    rows = querystore.list_queries(search, folder_filter)
    if not rows:
        st.sidebar.caption('No saved queries yet' if not search else 'No saved query matches')
    else:
        names = [row[0] for row in rows]
        picked = st.sidebar.selectbox('Query', names, key='sq_pick')
        sql_text, tags, folder = querystore.get_query(picked)
        details = ' · '.join(x for x in (f'Folder: {folder}' if folder else '', f'Tags: {tags}' if tags else '') if x)
        if details:
            st.sidebar.caption(details)
        st.sidebar.code(sql_text if len(sql_text) <= 400 else sql_text[:400] + ' ...', language='sql')
        load_col, new_col, delete_col = st.sidebar.columns(3)
        load_col.button('Load', on_click=load_saved_query, width='stretch', help='Load into the current tab')
        new_col.button('＋Tab', on_click=load_saved_query_new_tab, width='stretch', help='Open in a new query tab')
        delete_col.button('Delete', on_click=delete_saved_query, width='stretch')

    with st.sidebar.expander('Import / export saved queries'):
        download_button('⬇ Export all to JSON', lambda: querystore.export_queries_json().encode('utf-8'),
                        key='export_json', file_name='cloudsql_saved_queries.json', mime='application/json',
                        width='stretch')
        st.file_uploader('Import from JSON', type=['json'], key='import_file')
        st.checkbox('Overwrite queries with the same name', key='import_overwrite')
        st.button('Import', on_click=import_queries, width='stretch')

    with st.sidebar.expander('Recent runs'):
        history = querystore.list_history(30)
        if not history:
            st.caption('No queries run yet')
        else:
            labels = {h[0]: f"{h[6]} | {h[2]} | {h[3]} | {' '.join(h[1].split())[:50]}" for h in history}
            st.selectbox('Run', list(labels), key='hist_pick', format_func=labels.get)
            st.button('Load into editor', on_click=load_history_query)


# ---------- Downloads ----------

def _prepare_download(key):
    ss[f'prepared_{key}'] = True

def download_button(label, make_bytes, key, container=None, **kwargs):
    """Download button whose file is built only on demand, on every supported Streamlit version."""
    container = container or st
    if LAZY_DOWNLOADS:
        return container.download_button(label, data=make_bytes, key=key, **kwargs)
    # Older Streamlit: the first click builds the file, the second click saves it
    if ss.pop(f'prepared_{key}', False):
        return container.download_button(f'💾 Save {label.lstrip("⬇ ")}', data=make_bytes(), key=key, **kwargs)
    container.button(label, key=f'prepare_{key}', on_click=_prepare_download, args=(key,),
                     disabled=kwargs.get('disabled', False), help=kwargs.get('help'),
                     width=kwargs.get('width', 'content'))


# ---------- Results ----------

def to_excel_bytes(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    return buffer.getvalue()

# Plain dataframe grid: a pandas Styler renders every cell to HTML and uses far more memory
def show_results(tab):
    csv_data, info = tab['df'], tab['info']
    message = f"{info['rows']} rows in {info['elapsed']} s on {info['connection']}"
    if info['limit'] and info['rows'] >= info['limit']:
        message += f" · row limit {info['limit']} reached"

    file_base = ''.join(c if c.isalnum() or c in '-_' else '_' for c in tab['title']) or 'query_result'
    with st.container(horizontal=True, vertical_alignment='center'):
        st.caption(message, width='content')
        search = st.text_input('Filter results', key='result_filter', label_visibility='collapsed', width=300,
                               placeholder='🔍 Filter rows')
        view = csv_data
        if search and len(csv_data):
            mask = csv_data.astype(str).apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
            view = csv_data[mask]
            st.caption(f'{len(view)} match', width='content')
        # Export files are only built when the button is clicked
        download_button('⬇ CSV', lambda: view.to_csv(index=False).encode('utf-8'), key='download_csv',
                        file_name=f'{file_base}.csv', mime='text/csv')
        download_button('⬇ Excel', lambda: to_excel_bytes(view), key='download_xlsx', file_name=f'{file_base}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        disabled=len(view) > 1_048_575, help='Excel allows at most 1,048,575 data rows')
    st.dataframe(view, width='stretch', height=max(120, min(38 + 35 * len(view), 600)))

    with st.expander('SQL sent to the pod'):
        st.code(info['sql'], language='sql')


def run_active_tab(text, bind_values, row_limit, conn):
    connection_name, url, username, password = conn
    tab = active_tab()
    if not sqltools.clean_sql(text):
        tab['error'] = ('Enter a query to run', '')
        return
    if not (url and username and password):
        tab['error'] = ('Select or save a connection first', '')
        return
    sql_to_run = prepare_sql(text, bind_values, row_limit)
    # Free the previous result before fetching the new one
    tab['df'], tab['error'] = None, None
    started = time.perf_counter()
    try:
        with st.spinner(f'Running on {connection_name}...'):
            df = bip_client.run_query(url, username, password, sql_to_run, get_report_name(), get_timeout())
    except BipError as e:
        querystore.add_history(text, connection_name, 'error')
        tab['error'] = (str(e), e.detail)
        return
    except Exception as e:
        querystore.add_history(text, connection_name, 'error')
        tab['error'] = (f'Could not read the query result: {e}', '')
        return
    elapsed = round(time.perf_counter() - started, 2)
    querystore.add_history(text, connection_name, 'ok', len(df), elapsed)
    connections.set_last_sql(connection_name, text)
    tab['df'] = df
    tab['info'] = {'rows': len(df), 'elapsed': elapsed, 'limit': row_limit, 'sql': sql_to_run,
                   'connection': connection_name}


# ---------- Compare ----------

def request_compare():
    ss.compare_requested = ss.get('compare_with')

def compare_popover(connection_name):
    others = [c for c in connections.list_connections() if c != connection_name]
    with st.popover('⇄ Compare'):
        if not others:
            st.caption('Save a second connection (for example TEST next to DEV) to compare results')
            return
        st.selectbox(f'Compare {connection_name or "this connection"} with', others, key='compare_with')
        st.caption('Runs the query in the editor (with binds and row limit) on both connections and lists rows '
                   'that exist on only one side.')
        st.button('Compare', on_click=request_compare, type='primary')

def run_compare(sql_text, bind_values, row_limit, conn):
    connection_name, url, username, password = conn
    other = ss.pop('compare_requested', None)
    if not other:
        return
    ss.pop('compare_result', None)
    if not sqltools.clean_sql(sql_text):
        st.warning('Enter a query to compare')
        return
    sql_to_run = prepare_sql(sql_text, bind_values, row_limit)
    o_url, o_user, o_pw = connections.get_connection(other)
    try:
        with st.spinner(f'Running on {connection_name} and {other}...'):
            create_report(o_url, o_user, o_pw, get_datamodel_name(), get_report_name())
            a = bip_client.run_query(url, username, password, sql_to_run, get_report_name(), get_timeout())
            b = bip_client.run_query(o_url, o_user, o_pw, sql_to_run, get_report_name(), get_timeout())
            ss.compare_result = (connection_name, other, compare_frames(a, b, connection_name, other))
            del a, b
    except BipError as e:
        show_error(str(e), e.detail)
    except Exception as e:
        show_error(f'Compare failed: {e}')

def show_compare_result():
    if 'compare_result' not in ss:
        return
    a_name, b_name, result = ss.compare_result
    with st.container(border=True):
        head_col, close_col = st.columns([6, 1], vertical_alignment='center')
        head_col.markdown(f'**⇄ Compare {a_name} with {b_name}**')
        if close_col.button('✕ Hide', key='hide_compare', width='stretch'):
            ss.pop('compare_result', None)
            st.rerun()
        cols = st.columns(4)
        cols[0].metric(f'Rows on {a_name}', result['rows_a'])
        cols[1].metric(f'Rows on {b_name}', result['rows_b'])
        cols[2].metric(f'Only on {a_name}', result['only_a'])
        cols[3].metric(f'Only on {b_name}', result['only_b'])
        if result['only_cols_a'] or result['only_cols_b']:
            st.warning(f"Columns compared: only those in both. Only on {a_name}: {result['only_cols_a']} · "
                       f"only on {b_name}: {result['only_cols_b']}")
        if result['only_a'] == 0 and result['only_b'] == 0:
            st.success('Both connections return the same rows')
        else:
            st.dataframe(result['diff'], width='stretch')


# ---------- Schema browser ----------

def insert_select(statement):
    text = current_sql()
    set_editor_text((text.rstrip() + '\n\n' if text.strip() else '') + statement)
    flash('success', f"Added to {active_tab()['title']}. Open the SQL tab to see it")

def schema_browser(conn):
    connection_name, url, username, password = conn
    if not (connection_name and url and username and password):
        st.info('Select or save a connection first')
        return

    def run_sql(sql):
        return bip_client.run_query(url, username, password, sql, get_report_name(), get_timeout())

    status = metadata.object_status(connection_name)
    info_col, button_col = st.columns([3, 1], vertical_alignment='center')
    if status:
        info_col.caption(f'{status[0]:,} tables and views of {connection_name} cached locally '
                         f'(downloaded {status[1]}). They also feed the editor autocomplete.')
    else:
        info_col.info('Download the list of tables and views once. Searching is then instant and works offline, '
                      'and the editor can autocomplete table names.')
    if button_col.button('↻ Refresh object list' if status else '⬇ Download object list', width='stretch'):
        count = None
        try:
            with st.spinner('Downloading table and view names... this can take a minute on a big pod'):
                count = metadata.refresh_objects(connection_name, run_sql)
        except BipError as e:
            show_error(str(e), e.detail)
        except Exception as e:
            show_error(f'Could not download the object list: {e}')
        if count is not None:
            flash('success', f'Cached {count:,} tables and views')
            st.rerun()

    search = st.text_input('Search tables and views', key='schema_search', placeholder='e.g. PO_HEADERS')
    if not search.strip():
        return
    results = metadata.search_objects(connection_name, search)
    if not results:
        st.caption('Nothing found in the local list.' + ('' if status else ' Download the object list first.'))
        return
    if len(results) == 200:
        st.caption('Showing the first 200 matches, type more to narrow down')
    by_key = {f'{r[0]}.{r[1]}': r for r in results}
    labels = {k: f'{r[1]}  ·  {r[0]}  ·  {r[2]}' for k, r in by_key.items()}
    picked = st.selectbox('Object', list(by_key), key='schema_pick', format_func=labels.get)
    owner, table, object_type = by_key.get(picked, results[0])

    refresh = st.button('↻ Refresh columns', help='Columns are cached after the first look-up')
    try:
        with st.spinner(f'Fetching columns of {table}...'):
            columns = metadata.get_columns(connection_name, owner, table, run_sql, refresh=refresh)
    except BipError as e:
        show_error(str(e), e.detail)
        return
    st.dataframe(pd.DataFrame(columns, columns=['Column', 'Type', 'Nullable', '#']), hide_index=True,
                 width='stretch', height=min(38 + 35 * len(columns), 420))
    statement = metadata.select_statement(owner, table, columns)
    st.code(statement, language='sql')
    st.button('Insert this SELECT into the editor', on_click=insert_select, args=(statement,), type='primary')


# ---------- SQL tab ----------

def save_popover():
    with st.popover('💾 Save'):
        st.text_input('Query name (same name overwrites)', key='save_name')
        folders = [f for f in querystore.list_folders() if f]
        st.text_input('Folder (optional)', key='save_folder',
                      help='Existing folders: ' + ', '.join(folders) if folders else None)
        st.text_input('Tags (optional, comma separated)', key='save_tags')
        st.button('Save query', on_click=save_current_query, type='primary')


def sql_tab(conn):
    connection_name = conn[0]
    # Toolbar: query tabs on the left, query tools on the right
    tabs_col, tools_col = st.columns([3, 2], vertical_alignment='center')
    with tabs_col.container(horizontal=True, vertical_alignment='center'):
        # One button per query tab (buttons keep no state, so renaming a tab can never confuse them)
        for tab_id in ss.tab_order:
            st.button(ss.qtabs[tab_id]['title'], key=f'qtab_{tab_id}', on_click=switch_tab, args=(tab_id,),
                      type='primary' if tab_id == ss.active_tab else 'secondary')
        st.button('＋ New', on_click=add_tab, help='Open a new query tab', key='qtab_new')
        st.button('✕ Close', on_click=close_tab, help='Close this query tab', key='qtab_close')
    with tools_col.container(horizontal=True, horizontal_alignment='right', vertical_alignment='center'):
        row_limit = st.selectbox('Row limit', ROW_LIMITS, index=1, key='row_limit', label_visibility='collapsed',
                                 width=130, format_func=lambda v: f'{v:,} rows' if isinstance(v, int) else 'All rows',
                                 help='Maximum number of rows the pod sends back')
        st.button('Format', on_click=format_editor_sql, help='Re-indent the SQL and upper-case keywords')
        save_popover()
        compare_popover(connection_name)
    row_limit = None if row_limit == 'All' else row_limit
    tab = active_tab()

    run_requested, run_text = False, None
    if ss.get('plain_editor', False):
        ss.setdefault('sql_editor', tab['sql'])
        st.text_area('Enter valid query', height=EDITOR_HEIGHT, key='sql_editor', label_visibility='collapsed')
    else:
        value = sql_editor(tab['sql'], tab['version'], ss.active_tab,
                           words_url=metadata.words_url(connection_name) if connection_name else None,
                           extra_words=metadata.known_columns(connection_name, tab['sql']) if connection_name else [],
                           height=EDITOR_HEIGHT, key='ace_editor')
        # Ctrl+Enter in the editor runs the query (or the selected part of it) once
        if value and value.get('run') and value.get('tab') == ss.active_tab \
                and value.get('version') == tab['version'] and value.get('nonce') != ss.get('last_nonce'):
            ss.last_nonce = value['nonce']
            run_requested = True
            run_text = value.get('selection') or None
    tab['sql'] = current_sql()

    # Run button right under the editor, bind variables next to it
    with st.container(horizontal=True, vertical_alignment='center', key='run_row'):
        if st.button('▶ Run', type='primary', key='run_button',
                     help='Runs everything in the editor. Ctrl+Enter in the editor runs only the statement under '
                          'the cursor (blank line or ; separates statements) or the selected text. '
                          'Ctrl+Space shows suggestions.'):
            run_requested = True
        bind_values = bind_inputs(tab['sql'])

    if run_requested:
        run_active_tab(run_text or tab['sql'], bind_values, row_limit, conn)
    run_compare(tab['sql'], bind_values, row_limit, conn)

    if tab['error']:
        show_error(*tab['error'])
    elif isinstance(tab['df'], pd.DataFrame):
        show_results(tab)
    show_compare_result()


# Main function
def main():
    set_css_style()
    querystore.init_db()
    connections.init_db()
    metadata.init_db()
    migrated = connections.migrate_from_config(CONFIG_FILE)
    if migrated:
        flash('info', f"Moved connections {', '.join(migrated)} out of config.ini into the local database. "
                      'Their passwords are kept in the Windows Credential Manager when it is available.')
    init_tabs()
    ss.setdefault('plain_editor', use_plain_editor())

    conn = connection_sidebar()
    saved_queries_sidebar()

    st.write(f'Connection name : {conn[0]}')
    # Always-present container: messages must not shift the tabs below, or Streamlit resets the selected tab
    with st.container():
        show_flashes()

    sql_view, schema_view = st.tabs(['📝 SQL', '🗂 Schema browser'])
    with sql_view:
        sql_tab(conn)
    with schema_view:
        schema_browser(conn)


if __name__ == '__main__':
    main()
