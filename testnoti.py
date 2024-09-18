import mysql.connector
from mysql.connector import errors
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, messaging
import os
from dotenv import load_dotenv
import pytz

# 初始化 Firebase Admin SDK
cred = credentials.Certificate("busconncet-firebase-adminsdk-3q883-4a49b71c98.json")
firebase_admin.initialize_app(cred)
load_dotenv()
def connect_to_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

def send_notifications(results, max_retries=3):
    for result in results:
        message = messaging.Message(
            notification=messaging.Notification(
                title=f"路線{result['route_name']}通知",
                body=f"點擊以查看{result['neareststop']}最新資訊",
            ),
            token=result['token'],
            data={
                'click_action': f'/bus?route_name={result["route_name"]}'  # 設定通知的連結
            }
        )
        for attempt in range(max_retries):
            try:
                response = messaging.send(message)
                print(f"Notification sent successfully for route {result['route_name']}: {response}")
                break  # 如果成功，則退出重試循環
            except Exception as e:
                print(f"Attempt {attempt + 1} for route {result['route_name']} failed: {e}")
                if attempt + 1 == max_retries:
                    print("Max retries reached for route {result['route_name']}, giving up.")

def check_and_send_notifications():
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)

    # 取得當前時間，並轉換為 HH:MM:00 格式
    taiwan_tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(taiwan_tz).strftime("%H:%M:00")

    query = """
    SELECT * FROM user_notifications
    WHERE notification_time = %s
    """
    cursor.execute(query, (now,))
    results = cursor.fetchall()

    if results:
        send_notifications(results)  # 逐條發送通知

    cursor.close()
    db_connection.close()

if __name__ == "__main__":
    check_and_send_notifications()