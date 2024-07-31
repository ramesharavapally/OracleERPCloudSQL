import requests
import urllib.parse
import xml.etree.ElementTree as ET
import io
import zipfile
import base64
import os
import shutil
import tempfile


def custom_encode(string):
    encoded_string = urllib.parse.quote(string, safe='')  
    encoded_string = encoded_string.replace('~' , "%7E")  
    return encoded_string    

def __string_to_bool(s):
    true_values = {'true'}
    false_values = {'false'}

    if s.lower() in true_values:
        return True
    elif s.lower() in false_values:
        return False
    else:
        raise ValueError(f"Cannot convert {s} to bool.")



def __check_object_exists(username : str , password : str , url : str , object_name : str) -> bool:
    
    url = f'{url}//xmlpserver/services/v2/CatalogService?wsdl'    
    
    headers = {'Content-Type': 'application/soap+xml'}
    
    payload = f"""
                <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://xmlns.oracle.com/oxp/service/v2">
                    <soapenv:Header/>
                        <soapenv:Body>
                            <v2:objectExist>
                                <v2:reportObjectAbsolutePath>{object_name}</v2:reportObjectAbsolutePath>
                                <v2:userID>{username}</v2:userID>
                                <v2:password>{password}</v2:password>
                            </v2:objectExist>
                        </soapenv:Body>
                </soapenv:Envelope>
                """
    
    response = requests.request(method='POST', url=url, data=payload, headers=headers, auth=(username, password))
    if response.status_code == 200:
        response_text = response.text
        start_tag = "<objectExistReturn>"
        end_tag = "</objectExistReturn>"
        start_index = response_text.find(start_tag)
        end_index = response_text.find(end_tag)
        if start_index != -1 and end_index != -1:
            return __string_to_bool(response_text[start_index + len(start_tag):end_index].strip())                                    
        else:
            raise ValueError(f"Error while getting report status {response.status_code} {response.text}")
    else:
        raise ValueError(f"Error while checkign report exists {response.status_code} {response.text}")


def __copy_folder_to_temp(source_folder):
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()

    # Get the basename of the source folder to preserve the folder structure
    folder_name = os.path.basename(source_folder)
    destination_folder = os.path.join(temp_dir, folder_name)

    # Copy the entire folder to the temporary directory
    shutil.copytree(source_folder, destination_folder)

    return temp_dir , destination_folder    

def __remove_temp_folder(temp_folder):
    # Remove the temporary directory and all its contents
    shutil.rmtree(temp_folder)

def __update_username_in_metadata(file_path, new_username):
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Iterate over all 'entry' elements
    for entry in root.findall('.//entry'):
        key = entry.find('key').text
        if key == 'path':
            value = entry.find('value').text
            updated_value = value.replace('conversion.user', new_username)
            entry.find('value').text = updated_value
            break

    # Write the updated XML back to the file
    tree.write(file_path, encoding='UTF-8', xml_declaration=True)    
    
def __update_username_in_xdo_file(file_path, new_username):
    tree = ET.parse(file_path)
    root = tree.getroot()
    namespaces = {'ns': 'http://xmlns.oracle.com/oxp/xmlp'}
    data_model_elem = root.find('ns:dataModel', namespaces)
    
    if data_model_elem is not None:
         current_url = data_model_elem.attrib.get('url', '')
         updated_url = current_url.replace('Conversion.User', new_username)
         data_model_elem.set('url', updated_url)
         tree.write(file_path, encoding='utf-8', xml_declaration=True)
    else:
        raise ValueError(f'Unable to file .xdo file in {file_path}')    
    
    
def __zip_folder_to_base64(folder_path):
    # Create a buffer to hold the zip file in memory
    buffer = io.BytesIO()
    
    # Create a zip file in the buffer
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Walk through the directory
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                # Create the complete filepath of the file in the directory
                file_path = os.path.join(root, file)
                # Add file to the zip file, using a relative path
                zip_file.write(file_path, os.path.relpath(file_path, folder_path))
    
    # Get the zip file's bytes
    zip_bytes = buffer.getvalue()
    
    # Encode the zip file bytes to a base64 string
    base64_str = base64.b64encode(zip_bytes).decode('utf-8')
    
    return base64_str    
    
def __generate_base64_string(type : str , username : str) -> str:
    base64_data = None
    if type == 'xdm':
        xdm_path = r'..\reports\localuser\xdm'
        temp_folder , temp_xdm_folder = __copy_folder_to_temp(xdm_path)
        # print(temp_xdm_folder)
        xdm_metadata_path = r'{}\~metadata.meta'.format(temp_xdm_folder)        
        __update_username_in_metadata(xdm_metadata_path , username)
        base64_data = __zip_folder_to_base64(temp_xdm_folder)        
        __remove_temp_folder(temp_folder)
    
    if type == 'xdo':
        xdo_path = r'..\reports\localuser\xdo'
        temp_folder , temp_xdo_folder = __copy_folder_to_temp(xdo_path)
        # print(temp_xdo_folder)
        xdo_metadata_path = r'{}\~metadata.meta'.format(temp_xdo_folder)        
        xdo__report_path = r'{}\_report.xdo'.format(temp_xdo_folder)        
        __update_username_in_metadata(xdo_metadata_path , username)
        __update_username_in_xdo_file(xdo__report_path , username)
        base64_data = __zip_folder_to_base64(temp_xdo_folder)        
        __remove_temp_folder(temp_folder)
    return base64_data
        
    
def __upload_object(url , username , password , object_name , object_type ) ->  bool:
    url = f'{url}//xmlpserver/services/v2/CatalogService?wsdl'   
    
    object_name = object_name.rsplit('.', 1)[0] 
    
    headers = {'Content-Type': 'application/soap+xml'}
    
    payload = None
    
    if object_type == 'xdm':        
        payload = f"""
                <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://xmlns.oracle.com/oxp/service/v2">
                    <soapenv:Header/>
                        <soapenv:Body>
                            <v2:uploadObject>
                                <v2:reportObjectAbsolutePathURL>{object_name}</v2:reportObjectAbsolutePathURL>
                                <v2:objectType>xdmz</v2:objectType>
                                <v2:objectZippedData>{__generate_base64_string(object_type , username)}</v2:objectZippedData>
                                <v2:userID>{username}</v2:userID>
                                <v2:password>{password}</v2:password>
                            </v2:uploadObject>
                        </soapenv:Body>
                </soapenv:Envelope>
                    """
    elif object_type == 'xdo':
        payload = f"""
                <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://xmlns.oracle.com/oxp/service/v2">
                    <soapenv:Header/>
                        <soapenv:Body>
                            <v2:uploadObject>
                                <v2:reportObjectAbsolutePathURL>{object_name}</v2:reportObjectAbsolutePathURL>
                                <v2:objectType>xdoz</v2:objectType>
                                <v2:objectZippedData>{__generate_base64_string(object_type , username)}</v2:objectZippedData>
                                <v2:userID>{username}</v2:userID>
                                <v2:password>{password}</v2:password>
                            </v2:uploadObject>
                        </soapenv:Body>
                </soapenv:Envelope>
                    """
    
    else:
        raise ValueError(f"Invlaid object type provided {object_type}")
    
    response = requests.request(method='POST', url=url, data=payload, headers=headers, auth=(username, password))
    if response.status_code == 200:
        response_text = response.text
        start_tag = "<uploadObjectReturn>"
        end_tag = "</uploadObjectReturn>"
        start_index = response_text.find(start_tag)
        end_index = response_text.find(end_tag)
        if start_index != -1 and end_index != -1:
            return response_text[start_index + len(start_tag):end_index].strip() == f"{object_name}.{object_type}"
        else:
            raise ValueError(f"Error while getting report status {response.status_code} {response.text}")
    else:
        raise ValueError(f"Error while checkign report exists {response.status_code} {response.text}")
    
def create_report(url , username , password , datamodel_name , report_name):
    dm_result = __check_object_exists(username , password , url , datamodel_name )
    if not dm_result:
        result = __upload_object(url , username , password , datamodel_name , 'xdm')        
        if result == False:
            raise ValueError('Error while creating Datamodel')    
    report_result = __check_object_exists(username , password , url , report_name)
    if not report_result:
        result = __upload_object(url , username , password , report_name , 'xdo')        
        if result == False:
            raise ValueError('Error while creating report')        
