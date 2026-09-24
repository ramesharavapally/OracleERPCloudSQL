import streamlit as st
import requests
import base64
import pandas as pd
from io import BytesIO
import configparser
import os
import time
from reportutils import create_report
import querystore

# Set page configuration to wide mode by default
st.set_page_config(layout="wide" ,
                   page_title="Cloud SQL",
                   page_icon="🌊",)
CONFIG_FILE = 'config.ini'

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
        </style>
        """,
        unsafe_allow_html=True
    )

def get_report_name():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config['DEFAULT']['report_path']

def get_datamodel_name():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config['DEFAULT']['datamodel_path']

# Function to save or update connection details to a properties file
def save_or_update_connection_details(url, username, password, connection_name):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if connection_name in config:
        # Update existing connection details
        config[connection_name] = {'url': url, 'username': username, 'password': password}
        st.sidebar.success(f"Updated connection details for {connection_name}")
    else:
        # Save new connection details
        config[connection_name] = {'url': url, 'username': username, 'password': password}
        st.sidebar.success(f"Created new connection: {connection_name}")

    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)
    
    # Refresh the list of saved connections and select the newly created connection    
    # st.experimental_rerun()

# Function to load saved connections from the properties file
def load_saved_connections():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)    
    return config.sections()

# Function to get connection details based on the selected connection
def get_connection_details(connection_name):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config[connection_name]['url'], config[connection_name]['username'], config[connection_name]['password']

# Function to invoke SOAP API
# @st.cache_data
def invoke_soap_api(payload , url , username , password):
    # Define the URL of the SOAP API endpoint
    url = f'{url}/xmlpserver/services/ExternalReportWSSService?WSDL'
    USERNAME = username
    PASSWORD = password

    # Define headers for the SOAP request
    headers = {'Content-Type': 'application/soap+xml'}

    # Make the POST request to invoke the SOAP API
    response = requests.request(method='POST', url=url, data=payload, headers=headers, auth=(USERNAME, PASSWORD))
    

    # Check if the request was successful
    if response.status_code == 200:
        return response
    else:
        st.session_state.csv_data = ""
        st.error(f"Failed to invoke SOAP API. Status code: {response.status_code} {response.text}")

# Function to extract report bytes
def extract_report_bytes(response_text):
    start_tag = "<ns2:reportBytes>"
    end_tag = "</ns2:reportBytes>"
    start_index = response_text.find(start_tag)
    end_index = response_text.find(end_tag)
    if start_index != -1 and end_index != -1:
        return response_text[start_index + len(start_tag):end_index].strip()
    else:
        return None

# Function to decode base64 and display CSV
def decode_base64_and_display_csv(base64_data):    
    # Decode base64 data
    decoded_data = base64.b64decode(base64_data)

    # Read the decoded data as CSV
    csv_data = pd.read_csv(BytesIO(decoded_data))
    
    st.session_state.csv_data = csv_data
    show_results(csv_data)
    return csv_data

# Plain dataframe grid: a pandas Styler renders every cell to HTML and uses far more memory
def show_results(csv_data):
    st.dataframe(csv_data, width='stretch')

# ---------- Saved query / history callbacks (run before the page re-renders) ----------

def load_into_editor(sql_text, name=None):
    st.session_state.sql_editor = sql_text
    if name:
        st.session_state.save_name = name

def load_saved_query():
    sql_text, tags = querystore.get_query(st.session_state.sq_pick)
    if sql_text is not None:
        load_into_editor(sql_text, st.session_state.sq_pick)
        st.session_state.save_tags = tags or ''

def delete_saved_query():
    querystore.delete_query(st.session_state.sq_pick)
    st.session_state.flash = ('success', f"Deleted saved query '{st.session_state.sq_pick}'")

def save_current_query():
    name = st.session_state.get('save_name', '').strip()
    sql_text = st.session_state.get('sql_editor', '').strip()
    if not name or not sql_text:
        st.session_state.flash = ('warning', 'Enter a query name and some SQL before saving')
        return
    updated = querystore.save_query(name, sql_text, st.session_state.get('save_tags', '').strip())
    st.session_state.flash = ('success', f"{'Updated' if updated else 'Saved'} query '{name}'")

def load_history_query():
    load_into_editor(st.session_state.hist_pick[1])

def saved_queries_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader('Saved Queries')
    search = st.sidebar.text_input('Search name / tag / SQL', key='sq_search')
    names = [row[0] for row in querystore.list_queries(search)]
    if not names:
        st.sidebar.caption('No saved queries yet')
    else:
        picked = st.sidebar.selectbox('Query', names, key='sq_pick')
        sql_text, tags = querystore.get_query(picked)
        if tags:
            st.sidebar.caption(f'Tags: {tags}')
        st.sidebar.code(sql_text if len(sql_text) <= 400 else sql_text[:400] + ' ...', language='sql')
        load_col, delete_col = st.sidebar.columns(2)
        load_col.button('Load', on_click=load_saved_query, width='stretch')
        delete_col.button('Delete', on_click=delete_saved_query, width='stretch')

    with st.sidebar.expander('Recent runs'):
        history = querystore.list_history(30)
        if not history:
            st.caption('No queries run yet')
        else:
            st.selectbox('Run', history, key='hist_pick',
                         format_func=lambda h: f"{h[6]} | {h[3]} | {' '.join(h[1].split())[:50]}")
            st.button('Load into editor', on_click=load_history_query)

# Main function
def main():
    # Input fields for selecting saved connections    
    set_css_style()
    querystore.init_db()
    saved_connections = load_saved_connections()    
    selected_connection = st.sidebar.selectbox('Select Connection:', saved_connections)
    connection_name = selected_connection

    # Get connection details based on the selected connection
    if 'selected_connection' not in st.session_state:
        st.session_state.selected_connection = ""
        
    if selected_connection:        
        url, username, password  = get_connection_details(selected_connection) 
        if selected_connection != st.session_state.selected_connection :  
            try:          
                create_report(url , username , password , get_datamodel_name() , get_report_name())
            except Exception as e:
                st.error(f"Error occured while creating DM {e}")
        st.session_state.selected_connection = selected_connection
    else:
        url, username, password , connection_name= '', '', '' ,''        

    # Input fields for URL, username, and password
    connection_name = st.sidebar.text_input('Connection Name', value=connection_name)
    url_input = st.sidebar.text_input('API URL', value=url)
    username_input = st.sidebar.text_input('Username', value=username)
    password_input = st.sidebar.text_input('Password', type='password', value=password)

    # Save button to store or update connection details
    if st.sidebar.button('Save'):
        save_or_update_connection_details(url_input, username_input, password_input, connection_name)        
        try:            
            create_report(url_input , username_input , password_input , get_datamodel_name() , get_report_name())
        except Exception as e:
            st.error(f"Error occured while creating DM in Save  {e}")
                        
        st.session_state.selected_connection = selected_connection

    saved_queries_sidebar()

    st.write(f'Connection name : {connection_name}')
    if 'flash' in st.session_state:
        level, message = st.session_state.pop('flash')
        getattr(st, level)(message)

    # Input field for user to enter data
    user_input = st.text_area('Enter valid query', height=250, key='sql_editor')
    
    submit =  st.button('Run')

    with st.expander('💾 Save query'):
        name_col, tags_col = st.columns([2, 1])
        name_col.text_input('Query name (same name overwrites)', key='save_name')
        tags_col.text_input('Tags (optional, comma separated)', key='save_tags')
        st.button('Save query', on_click=save_current_query)

    # Button to submit the input data
    if submit:                
        started = time.perf_counter()
        # Convert user input to base64
        base64_input = base64.b64encode(user_input.encode()).decode()

        # Construct the SOAP request payload with the base64 input
        soap_payload = f"""
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
           <soap:Header/>
           <soap:Body>
              <pub:runReport>
                 <pub:reportRequest>
                    <pub:attributeFormat>csv</pub:attributeFormat>
                    <pub:flattenXML>false</pub:flattenXML>
                    <pub:parameterNameValues>
                       <pub:item>
                          <pub:name>query1</pub:name>
                          <pub:values>
                             <pub:item>{base64_input}</pub:item>
                          </pub:values>
                       </pub:item>
                    </pub:parameterNameValues>
                    <pub:reportAbsolutePath>{get_report_name()}</pub:reportAbsolutePath>
                    <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
                 </pub:reportRequest>
              </pub:runReport>
           </soap:Body>
        </soap:Envelope>
        """

        # Invoke the SOAP API with the constructed payload
        api_response = invoke_soap_api(soap_payload , url_input , username_input , password_input)
        if api_response:
            report_bytes = extract_report_bytes(str(api_response.text))
            # Replace None values with 'null' for better display
            report_bytes = report_bytes if report_bytes is not None else 'null'
            # Decode base64 response and display CSV data
            try:
                csv_data = decode_base64_and_display_csv(report_bytes)
            except Exception as e:
                st.session_state.csv_data = ""
                querystore.add_history(user_input, connection_name, 'error')
                st.error(f"Could not read the query result: {e}")
            else:
                elapsed = round(time.perf_counter() - started, 2)
                querystore.add_history(user_input, connection_name, 'ok', len(csv_data), elapsed)
                st.caption(f'{len(csv_data)} rows in {elapsed} s')
        else:
            querystore.add_history(user_input, connection_name, 'error')
    # Set the selected connection to the newly created or updated connection
    else:
        if 'csv_data' not in st.session_state:
            st.session_state.csv_data = ""
        elif 'csv_data'  in st.session_state:
            try:
                if isinstance(st.session_state.csv_data, pd.DataFrame):
                    show_results(st.session_state.csv_data)
            except Exception as e:
                pass
    st.session_state.selected_connection = connection_name

if __name__ == '__main__':
    main()


if 'user_input' not in st.session_state:
        st.session_state.user_input = ""