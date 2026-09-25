import base64
import html
import re
from io import BytesIO

import pandas as pd
import requests

# (connect timeout, read timeout) in seconds. Long reports may take minutes, but a dead network should fail fast.
DEFAULT_TIMEOUT = (15, 600)

_session = requests.Session()


class BipError(Exception):
    """An error from BI Publisher, with a short message and the full detail for troubleshooting."""

    def __init__(self, message, detail=''):
        super().__init__(message)
        self.detail = detail


def readable_error(status_code, body):
    """Turn a SOAP fault / HTTP error into one readable line."""
    if status_code == 401:
        return 'Invalid username or password (HTTP 401)'
    if status_code == 403:
        return 'This user is not allowed to run the report (HTTP 403). Check the BI roles of the user'
    if status_code == 404:
        return 'Report service not found (HTTP 404). Check the API URL of the connection'

    text = html.unescape(body or '')
    ora = re.search(r'(ORA-\d{5}:[^\n<]*)', text)
    if ora:
        return ora.group(1).strip()
    fault = (re.search(r'<(?:\w+:)?Text[^>]*>(.*?)</(?:\w+:)?Text>', text, re.DOTALL)
             or re.search(r'<faultstring[^>]*>(.*?)</faultstring>', text, re.DOTALL))
    if fault:
        message = ' '.join(fault.group(1).split())
        # BIP wraps the useful part in long Java exception chains; keep the last "Exception:" message
        parts = [p.strip() for p in re.split(r'\w+(?:\.\w+)*Exception:', message) if p.strip()]
        return (parts[-1] if parts else message)[:500]
    return f'HTTP {status_code}: {" ".join(re.sub(r"<[^>]+>", " ", text).split())[:300]}'


def post_soap(url, payload, username, password, timeout=DEFAULT_TIMEOUT):
    headers = {'Content-Type': 'application/soap+xml'}
    try:
        response = _session.post(url, data=payload, headers=headers, auth=(username, password), timeout=timeout)
    except requests.exceptions.ConnectTimeout:
        raise BipError('Could not reach the pod in time. Check the URL, VPN or proxy')
    except requests.exceptions.ReadTimeout:
        raise BipError(f'The pod did not answer within {timeout[1]} seconds. Try a smaller row limit or a narrower query')
    except requests.exceptions.ConnectionError as e:
        raise BipError('Could not connect to the pod. Check the URL and your network', str(e))
    if response.status_code != 200:
        raise BipError(readable_error(response.status_code, response.text), response.text)
    return response


def _run_report_payload(sql, report_path):
    base64_input = base64.b64encode(sql.encode()).decode()
    return f"""
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
                    <pub:reportAbsolutePath>{report_path}</pub:reportAbsolutePath>
                    <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
                 </pub:reportRequest>
              </pub:runReport>
           </soap:Body>
        </soap:Envelope>
        """


def extract_report_bytes(response_text):
    match = re.search(r'<(?:\w+:)?reportBytes>(.*?)</(?:\w+:)?reportBytes>', response_text, re.DOTALL)
    return match.group(1).strip() if match else None


def run_query(url, username, password, sql, report_path, timeout=DEFAULT_TIMEOUT):
    """Run a SELECT through the BI Publisher report and return the result as a DataFrame."""
    response = post_soap(f'{url}/xmlpserver/services/ExternalReportWSSService?WSDL',
                         _run_report_payload(sql, report_path), username, password, timeout)
    report_bytes = extract_report_bytes(response.text)
    if report_bytes is None:
        raise BipError(readable_error(response.status_code, response.text), response.text)
    decoded = base64.b64decode(report_bytes)
    if not decoded.strip():
        return pd.DataFrame()
    return pd.read_csv(BytesIO(decoded))
