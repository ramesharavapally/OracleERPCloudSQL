import requests


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
                                <v2:objectZippedData>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</v2:objectZippedData>
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
                                <v2:objectZippedData>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</v2:objectZippedData>
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
    print('Done')
