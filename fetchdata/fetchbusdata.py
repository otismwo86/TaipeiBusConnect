import requests
import json
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()
app_id = os.getenv('APP_ID')
app_key = os.getenv('APP_KEY')

auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
route_url = "https://tdx.transportdata.tw/api/basic/v2/Bus/Route/City/Taipei?%24format=JSON"
stops_url = "https://tdx.transportdata.tw/api/basic/v2/Bus/DisplayStopOfRoute/City/Taipei?%24format=JSON"
buffer_url = "https://tdx.transportdata.tw/api/basic/v2/Bus/RouteFare/City/Taipei?%24format=JSON"

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

# 建立資料庫連接
try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    cursor = connection.cursor()

    # 建立表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_route (
        id INT AUTO_INCREMENT PRIMARY KEY,
        route_name VARCHAR(255) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_stop (
        id INT AUTO_INCREMENT PRIMARY KEY,
        route_id INT,
        route_uid VARCHAR(255),
        start VARCHAR(255),
        end VARCHAR(255),
        direction INT,
        stops TEXT,
        FOREIGN KEY (route_id) REFERENCES bus_route(id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_buffer (
        id INT AUTO_INCREMENT PRIMARY KEY,
        route_id INT,
        direction INT,
        buffer_start VARCHAR(255),
        buffer_end VARCHAR(255),
        FOREIGN KEY (route_id) REFERENCES bus_route(id)
    );
    """)

    # 暫時禁用外鍵檢查
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    # 清空表資料並重置 AUTO_INCREMENT
    cursor.execute("TRUNCATE TABLE bus_stop")
    cursor.execute("TRUNCATE TABLE bus_route")
    cursor.execute("TRUNCATE TABLE bus_buffer")
    # 恢復外鍵檢查
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    # 認證並取得資料
    auth = Auth(app_id, app_key)
    auth_response = requests.post(auth_url, data=auth.get_auth_header())
    auth_response.raise_for_status()
    data = Data(auth_response)

    # 獲取路線資料
    route_response = requests.get(route_url, headers=data.get_data_header())
    route_response.raise_for_status()
    route_data = route_response.json()

    # 獲取站點資料
    stops_response = requests.get(stops_url, headers=data.get_data_header())
    stops_response.raise_for_status()
    stops_data = stops_response.json()

    # 獲取 buffer 資料
    buffer_response = requests.get(buffer_url, headers=data.get_data_header())
    buffer_response.raise_for_status()
    buffer_data = buffer_response.json()

    # 將資料轉換為特定格式
    def transform_data(route_data, stops_data):
        route_dict = {route['RouteUID']: route for route in route_data}
        transformed_routes = []

        for stop_route in stops_data:
            route_uid = stop_route['RouteUID']
            if route_uid in route_dict:
                route_info = route_dict[route_uid]
                route_name = route_info['RouteName']['Zh_tw']
                direction = stop_route['Direction']
                stops = [stop['StopName']['Zh_tw'] for stop in stop_route['Stops']]
                if direction == 0:
                    start = route_info['DepartureStopNameZh']
                    end = route_info['DestinationStopNameZh']
                else:
                    start = route_info['DestinationStopNameZh']
                    end = route_info['DepartureStopNameZh']
                transformed_route = {
                    'RouteName': route_name,
                    'RouteID': route_uid,
                    'start': start,
                    'end': end,
                    'Direction': direction,
                    '路線': stops
                }
                
                transformed_routes.append(transformed_route)
        
        return transformed_routes

    transformed_data = transform_data(route_data, stops_data)

    # 建立 route_name 到 route_id 的映射字典
    route_id_map = {}

    # 批量插入 bus_route 和 bus_stop 資料
    bus_stop_data = []

    for route in transformed_data:
        route_name = route['RouteName']
        cursor.execute("SELECT id FROM bus_route WHERE route_name = %s", (route_name,))
        result = cursor.fetchone()
        if result:
            route_id = result[0]
        else:
            cursor.execute("INSERT INTO bus_route (route_name) VALUES (%s)", (route_name,))
            route_id = cursor.lastrowid
        route_id_map[route_name] = route_id  # 儲存到映射字典

        stops = json.dumps(route['路線'], ensure_ascii=False)
        bus_stop_data.append((route_id, route['RouteID'], route['start'], route['end'], route['Direction'], stops))

    # 批量插入 bus_stop 資料
    cursor.executemany("""
        INSERT INTO bus_stop (route_id, route_uid, start, end, direction, stops) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """, bus_stop_data)
    connection.commit()

    # 批量插入 bus_buffer 資料
    bus_buffer_data = []

    for route in buffer_data:
        route_name = route['RouteName']
        route_id = route_id_map.get(route_name)
        if route_id is not None:
            section_fares = route.get('SectionFares', [])
            for section in section_fares:
                buffer_zones = section.get('BufferZones', [])
                for buffer_zone in buffer_zones:
                    direction = buffer_zone['Direction']
                    buffer_start = buffer_zone['FareBufferZoneOrigin']['StopName']
                    buffer_end = buffer_zone['FareBufferZoneDestination']['StopName']
                    bus_buffer_data.append((route_id, direction, buffer_start, buffer_end))

    cursor.executemany("""
        INSERT INTO bus_buffer (route_id, direction, buffer_start, buffer_end)
        VALUES (%s, %s, %s, %s)
    """, bus_buffer_data)
    connection.commit()

    print("資料已成功存入數據庫")

except mysql.connector.Error as err:
    print(f"Error: {err}")
finally:
    if connection.is_connected():
        cursor.close()
        connection.close()
        print("MySQL connection is closed")
