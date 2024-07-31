DECLARE
    TYPE refcursor IS ref CURSOR;
    xdo_cursor        REFCURSOR;
    l_query VARCHAR2(32000);
	
    FUNCTION get_query (p_query IN VARCHAR2)
    RETURN VARCHAR2
    IS      
    BEGIN        
        RETURN utl_raw.cast_to_varchar2(utl_encode.base64_decode(UTL_RAW.CAST_TO_RAW( p_query )));    
    END;
BEGIN
    l_query := get_query(:query1);

    OPEN :xdo_cursor FOR
      l_query;
END;

--https://www.oracleshare.com/pl-sql-block-from-fusion-bi-report-using-procedure-call/
--https://dzone.com/articles/injecting-sql-queries-with-oracle-erp-cloud
--/fscmRestApi/resources/11.13.18.05/dataSecurities assign data access to user
--Invoke report from myfolder
--https://docs.oracle.com/cd/E80149_01/bip/BIPRD/GUID-F788B306-99F6-432E-BCD5-F45046D31684.htm#BIPRD3321