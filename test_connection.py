import os
from dotenv import load_dotenv
from google.oauth2 import service_account
import googleapiclient.discovery

# Load env variables
load_dotenv()

# Test 1: Check OpenAI key
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print("✅ OpenAI API Key loaded")
else:
    print("❌ OpenAI API Key NOT found")

# Test 2: Check Google Sheets connection
try:
    creds = service_account.Credentials.from_service_account_file(
        'data/credentials.json',
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = googleapiclient.discovery.build('sheets', 'v4', credentials=creds)
    
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    result = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    print(f"✅ Google Sheets Connected! Sheet: {result['properties']['title']}")
except Exception as e:
    print(f"❌ Google Sheets Error: {e}")

print("\n🎉 All connections ready!")