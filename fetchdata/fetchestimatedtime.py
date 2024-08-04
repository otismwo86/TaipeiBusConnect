import mysql.connector
import requests
import os
from dotenv import load_dotenv

load_dotenv()
app_id = os.getenv('APP_ID')
app_key = os.getenv('APP_KEY')

auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
estimated_url = 'https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/Taipei?%24format=JSON'

class Auth:
    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key

    def get_auth_header(self):
        return {
            'content-type': 'application/x-www-form-urlencoded',
            'grant_type': 'client_credentials',
            'client_id': self.app_id,
            'client_secret': self.app_key
        }

class Data:
    def __init__(self, auth_response):
        self.access_token = auth_response.json().get('access_token')

    def get_data_header(self):
        return {
            'authorization': 'Bearer ' + self.access_token,
            'Accept-Encoding': 'gzip'
        }

# 認證並獲取 token
auth = Auth(app_id, app_key)
auth_response = requests.post(auth_url, data=auth.get_auth_header())
auth_response.raise_for_status()
data = Data(auth_response)

# 獲取buffer資料
estimated_response = requests.get(estimated_url, headers=data.get_data_header())
estimated_response.raise_for_status()
estimated_data = estimated_response.json()

# 連接到資料庫
connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)
cursor = connection.cursor()

# 創建或更新狀態表
cursor.execute("""
CREATE TABLE IF NOT EXISTS table_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    current_table VARCHAR(255)
);
""")

# 獲取當前表的名稱
cursor.execute("SELECT current_table FROM table_status")
result = cursor.fetchone()
current_table = result[0] if result else "bus_estimated"

# 決定更新的表
backup_table = "bus_estimated_backup"
update_table = backup_table if current_table == "bus_estimated" else "bus_estimated"

# 創建更新表（如果不存在）
cursor.execute(f"""
CREATE TABLE IF NOT EXISTS {update_table} (
    id INT AUTO_INCREMENT PRIMARY KEY,
    route_name VARCHAR(255),
    stop_name VARCHAR(255),
    direction INT,
    estimated_time INT,
    stop_status INT
);
""")
# 清空更新表的資料
cursor.execute(f"TRUNCATE TABLE {update_table}")

# 準備批量插入的資料
batch_size = 1000
data_to_insert = []

for item in estimated_data:
    route_name = item['RouteName']['Zh_tw']
    stop_name = item['StopName']['Zh_tw']
    direction = item['Direction']
    estimated_time = item.get('EstimateTime', None)
    stop_status = item.get('StopStatus', None)
    
    data_to_insert.append((route_name, stop_name, direction, estimated_time, stop_status))

    # 批量插入
    if len(data_to_insert) >= batch_size:
        cursor.executemany(f"""
            INSERT INTO {update_table} (route_name, stop_name, direction, estimated_time, stop_status)
            VALUES (%s, %s, %s, %s, %s)
        """, data_to_insert)
        connection.commit()
        data_to_insert = []  # 清空列表以便下一批資料

# 插入剩餘的資料
if data_to_insert:
    cursor.executemany(f"""
        INSERT INTO {update_table} (route_name, stop_name, direction, estimated_time, stop_status)
        VALUES (%s, %s, %s, %s, %s)
    """, data_to_insert)
    connection.commit()

# 更新狀態表
cursor.execute("TRUNCATE TABLE table_status")
cursor.execute("INSERT INTO table_status (current_table) VALUES (%s)", (update_table,))
connection.commit()

# 關閉連接
cursor.close()
connection.close()

print(f"資料已成功更新至 {update_table} 表")