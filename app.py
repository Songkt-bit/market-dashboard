import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

ECOS_API_KEY = "SD3KP3QMBSUDCP8GK0NM"
STAT_CODE = "901Y118"
ITEM_CODE = "T002"
START_DATE = "200001"
END_DATE = datetime.today().strftime("%Y%m")
ROW_LIMIT = 1000
GOOGLE_SHEET_NAME = "export"
WORKSHEET_NAME = "exportdata"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.join(BASE_DIR, "credential.json")

def fetch_and_prepare_data():
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr/1/{ROW_LIMIT}/"
        f"{STAT_CODE}/M/{START_DATE}/{END_DATE}/{ITEM_CODE}"
    )
    
    print("1. 한국은행 ECOS 서버에서 수출 데이터 수집 중...")
    response = requests.get(url)
    if response.status_code != 200:
        print("API 요청 실패:", response.status_code)
        return pd.DataFrame()
        
    data = response.json()
    if "StatisticSearch" not in data:
        print("데이터 구조 오류:", data)
        return pd.DataFrame()
        
    rows = data["StatisticSearch"]["row"]
    df = pd.DataFrame(rows)
    
    df_filtered = df[['TIME', 'ITEM_NAME1', 'DATA_VALUE']].copy()
    df_filtered.columns = ['Date', 'Item', 'Value']
    df_filtered['Value'] = pd.to_numeric(df_filtered['Value'], errors='coerce')
    
    # 💡 1. YoY(%) 계산 (전년 동월 대비)
    df_filtered['YoY (%)'] = (df_filtered['Value'].pct_change(12) * 100).round(2)
    
    # 💡 2. Date 형식 변환 (YYYYMM -> YY.MM, 예: 200001 -> 00.01)
    df_filtered['Date'] = df_filtered['Date'].astype(str)
    df_filtered['Date'] = df_filtered['Date'].str[2:4] + '.' + df_filtered['Date'].str[4:6]
    
    # 💡 3. 필요 없는 'Item', 'Value'(수출금액) 칸은 제거하고 Date와 YoY(%)만 남김
    df_final = df_filtered[['Date', 'YoY (%)']].dropna().copy()
    
    print(f"-> 데이터 가공 완료! 총 {len(df_final)}행이 준비되었습니다.")
    return df_final

def update_google_sheet(df):
    if df.empty:
        print("업데이트할 데이터가 없습니다.")
        return
        
    print("2. 구글 시트 인증 및 연결 중...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CRED_PATH, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)
    
    print("3. 구글 시트에 정돈된 데이터 업로드 및 덮어쓰기 중...")
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("✨ [성공] 구글 시트가 YY.MM 및 YoY(%) 형태로 깔끔하게 업데이트되었습니다!")

if __name__ == "__main__":
    print("--- 수출 데이터 자동 업데이트 스크립트 시작 ---")
    df_data = fetch_and_prepare_data()
    if not df_data.empty:
        update_google_sheet(df_data)
