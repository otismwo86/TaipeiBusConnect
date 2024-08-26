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

def send_batch_notifications(results):
    batch_size = 500  # 每批次最多發送 500 個通知
    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]  # 分批次
        messages = [
            messaging.Message(
                notification=messaging.Notification(
                    title=f"路線{result['route_name']}通知",
                    body=f"點擊以查看{result['neareststop']}最新資訊",
                ),
                token=result['token'],
                    data={
                        'click_action': f'/bus?route_name={result["route_name"]}'  # 設定通知的連結
                }
            ) for result in batch
        ]
        try:
            response = messaging.send_all(messages)
            print(f"Batch notification sent successfully: {response}")
        except Exception as e:
            print(f"Failed to send batch notification: {e}")

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
        send_batch_notifications(results)  # 分批次發送通知

    cursor.close()
    db_connection.close()

if __name__ == "__main__":
    check_and_send_notifications()