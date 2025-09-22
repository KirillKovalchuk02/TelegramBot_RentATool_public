from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from google.oauth2 import service_account 
import pandas as pd



from config import SCOPES, SERVICE_ACCOUNT_FILE, SAMPLE_RANGE, SAMPLE_SPREADSHEET_ID



def get_table_gsh(scopes: list, service_account_json: str, sheet_range: str, spreadsheet_id: str)-> pd.DataFrame:
    credentials = None
    credentials = service_account.Credentials.from_service_account_file(service_account_json, scopes=scopes)


    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()
    #Fetch values from the sheet
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_range).execute()
    values = result.get('values', [])

    df = pd.DataFrame(values)
    df.columns = df.iloc[0]
    df = df.drop(0, axis=0).reset_index(drop=True)

    return df

