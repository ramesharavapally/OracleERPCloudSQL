import streamlit as st
import requests
import base64
import pandas as pd
from io import BytesIO
import configparser
import os
from reportutils import create_report
import urllib.parse

# Set page configuration to wide mode by default
st.set_page_config(layout="wide" ,
                   page_title="Oracle ERP Local User SQL",
                   page_icon="🗄️",
                   initial_sidebar_state="expanded")
pd.set_option("styler.render.max_elements", 50000000)
CONFIG_FILE = 'config.ini'

def set_css_style():
    st.markdown(
        """
        <style>
        /* Modern color scheme and improved UI */
        :root {
            --primary-color: #0066cc;
            --secondary-color: #f0f2f6;
        }
        
        /* Header styling */
        .main-header {
            background: linear-gradient(90deg, #0066cc 0%, #004d99 100%);
            padding: 1.5rem 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .main-header h1 {
            color: white !important;
            margin: 0 !important;
            font-size: 2rem !important;
            font-weight: 600 !important;
        }
        
        .main-header p {
            color: #e0e0e0 !important;
            margin: 0.5rem 0 0 0 !important;
            font-size: 0.95rem !important;
        }
        
        /* Sidebar improvements */
        .css-1d391kg, [data-testid="stSidebar"] {
            background-color: #f8f9fa;
        }
        
        .sidebar-section {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        .sidebar-section h3 {
            color: #0066cc;
            font-size: 1rem;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }
        
        /* Query editor styling */
        textarea {
            color: #1a1a1a !important;
            font-size: 14px !important;
            font-family: "Source Code Pro", "Courier New", monospace !important;
            font-optical-sizing: auto !important;
            background-color: #f8f9fa !important;
            border: 2px solid #e0e0e0 !important;
            border-radius: 8px !important;
            padding: 12px !important;
            line-height: 1.6 !important;
        }
        
        textarea:focus {
            border-color: #0066cc !important;
            box-shadow: 0 0 0 2px rgba(0, 102, 204, 0.1) !important;
        }
        
        /* Button styling */
        .stButton > button {
            background: linear-gradient(90deg, #0066cc 0%, #0052a3 100%);
            color: white;
            border: none;
            padding: 0.6rem 2rem;
            font-weight: 500;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            transform: translateY(-1px);
        }
        
        /* Info boxes */
        .info-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
        }
        
        .success-box {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
        }
        
        /* Status indicators */
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-connected {
            background-color: #38ef7d;
            box-shadow: 0 0 8px rgba(56, 239, 125, 0.6);
        }
        
        .status-disconnected {
            background-color: #ff6b6b;
        }
        
        /* Dataframe improvements */
        .dataframe {
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        
        /* Input fields */
        .stTextInput > div > div > input,
        .stSelectbox > div > div > select {
            border-radius: 6px;
            border: 1px solid #e0e0e0;
        }
        
        .stTextInput > div > div > input:focus,
        .stSelectbox > div > div > select:focus {
            border-color: #0066cc;
            box-shadow: 0 0 0 2px rgba(0, 102, 204, 0.1);
        }
        
        /* Keyboard shortcuts hint */
        .shortcuts-hint {
            background: #f8f9fa;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            color: #666;
            margin: 1rem 0;
        }
        
        .shortcuts-hint kbd {
            background: white;
            border: 1px solid #ccc;
            border-radius: 3px;
            padding: 2px 6px;
            font-family: monospace;
            font-size: 0.9em;
        }
        
        /* Connection status */
        .connection-info {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #0066cc;
            margin: 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
def custom_encode(string):
    encoded_string = urllib.parse.quote(string, safe='')  
    encoded_string = encoded_string.replace('~' , "%7E")  
    return encoded_string    

def get_report_name(user_name: str):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    xdo_name = config['DEFAULT']['report_path']
    xdo_name = f"/~{user_name}{xdo_name}"    
    return xdo_name

def get_datamodel_name(user_name):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    xdm_name = config['DEFAULT']['datamodel_path']
    xdm_name = f"/~{user_name}{xdm_name}"    
    return xdm_name

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
    
    # Store in session state for display
    st.session_state.csv_data = csv_data

# Main function
def main():
    # Apply custom CSS
    set_css_style()
    
    # Display header
    st.markdown("""
        <div class="main-header">
            <h1>🗄️ Oracle ERP Local User SQL Console</h1>
            <p>Execute SQL queries against Oracle ERP Cloud with local user credentials</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Sidebar configuration
    with st.sidebar:
        st.markdown("### 🔌 Connection Management")
        
        # Load saved connections
        saved_connections = load_saved_connections()    
        selected_connection = st.selectbox('Select Connection:', saved_connections, help="Choose a saved connection or create a new one")
        connection_name = selected_connection

        # Get connection details based on the selected connection
        if 'selected_connection' not in st.session_state:
            st.session_state.selected_connection = ""
            
        if selected_connection:        
            url, username, password  = get_connection_details(selected_connection) 
            if selected_connection != st.session_state.selected_connection :  
                try:          
                    create_report(url , username , password , get_datamodel_name(username) , get_report_name(username))
                except Exception as e:
                    st.error(f"Error occured while creating DM {e}")
            st.session_state.selected_connection = selected_connection
        else:
            url, username, password , connection_name= '', '', '' ,''        

        st.markdown("---")
        st.markdown("### ⚙️ Connection Details")
        
        # Input fields for connection details
        connection_name = st.text_input('Connection Name', value=connection_name, help="A friendly name for this connection")
        url_input = st.text_input('API URL', value=url, help="Oracle ERP Cloud instance URL")
        username_input = st.text_input('Username', value=username, help="Your Oracle ERP local username")
        password_input = st.text_input('Password', type='password', value=password, help="Your Oracle ERP password")

        # Save button
        if st.button('💾 Save Connection', use_container_width=True):
            save_or_update_connection_details(url_input, username_input, password_input, connection_name)        
            try:            
                create_report(url_input , username_input , password_input , get_datamodel_name(username_input) , get_report_name(username_input))
            except Exception as e:
                st.error(f"Error occured while creating DM in Save  {e}")
                            
            st.session_state.selected_connection = selected_connection

        st.markdown("---")
        
        # Add helpful tips
        with st.expander("💡 Quick Tips"):
            st.markdown("""
            - **Save connections** for quick access
            - Use **Ctrl+Enter** in query box to run
            - Results can be **exported** as CSV
            - Query history is **automatically saved**
            - This console uses **local user** credentials
            """)
        
        with st.expander("📚 Example Queries"):
            st.code("""
-- Get all suppliers
SELECT * FROM suppliers 
LIMIT 10;

-- Check purchase orders
SELECT po_number, supplier_name 
FROM purchase_orders 
WHERE status = 'APPROVED';
            """, language="sql")

    # Main content area
    # Connection status
    status_icon = "🟢" if connection_name else "🔴"
    status_text = f"Connected to: **{connection_name}**" if connection_name else "No connection selected"
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"""
            <div class="connection-info">
                {status_icon} {status_text}
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
            <div class="shortcuts-hint">
                💡 <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to run
            </div>
        """, unsafe_allow_html=True)
    
    # Query editor
    st.markdown("### 📝 SQL Query Editor")
    user_input = st.text_area('Enter valid query', height=250, 
                                placeholder="-- Enter your SQL query here\nSELECT * FROM your_table LIMIT 10;",
                                label_visibility="collapsed")
    
    # Action buttons
    col1, col2, col3, col4 = st.columns([1, 1, 1, 6])
    with col1:
        submit = st.button('▶️ Run Query', type="primary", use_container_width=True)
    with col2:
        if st.button('🗑️ Clear', use_container_width=True):
            st.session_state.csv_data = ""
            st.rerun()
    with col3:
        if 'csv_data' in st.session_state and isinstance(st.session_state.csv_data, pd.DataFrame):
            csv = st.session_state.csv_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export CSV",
                data=csv,
                file_name="query_results.csv",
                mime="text/csv",
                use_container_width=True
            )

    # Button to submit the input data
    if submit:
        if not user_input.strip():
            st.warning("⚠️ Please enter a SQL query before running.")
        elif not connection_name:
            st.error("❌ Please select or create a connection first.")
        else:
            with st.spinner('🔄 Executing query...'):
                try:                
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
                                <pub:reportAbsolutePath>{get_report_name(username_input)}</pub:reportAbsolutePath>
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
                        decode_base64_and_display_csv(report_bytes)
                        st.success("✅ Query executed successfully!")
                except Exception as e:
                    st.error(f"❌ Error executing query: {str(e)}")
    
    # Display results section
    st.markdown("---")
    st.markdown("### 📊 Query Results")
    
    # Set the selected connection to the newly created or updated connection
    if 'csv_data' not in st.session_state:
        st.session_state.csv_data = ""
    
    if 'csv_data' in st.session_state and isinstance(st.session_state.csv_data, pd.DataFrame):
        try:
            # Display row count
            row_count = len(st.session_state.csv_data)
            col_count = len(st.session_state.csv_data.columns)
            
            st.info(f"📈 Results: {row_count} rows × {col_count} columns")
            
            # Display the dataframe with enhanced styling
            st.dataframe(
                st.session_state.csv_data.style.set_caption("Query Results").set_table_styles([{
                    'selector': 'th',
                    'props': [('font-weight', 'bold'), ('background-color', '#0066cc'), ('color', 'white')]
                }]), 
                width=5000,
                height=400
            )
        except Exception as e:
            st.error(f"Error displaying results: {str(e)}")
    elif not submit:
        st.info("👆 Enter a SQL query above and click 'Run Query' to see results here.")
    
    st.session_state.selected_connection = connection_name

if __name__ == '__main__':
    main()


if 'user_input' not in st.session_state:
        st.session_state.user_input = ""