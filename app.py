import json
import fastapi
from fastapi import *
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import mysql.connector
from mysql.connector import errors
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, messaging
from pydantic import BaseModel
from router.auth import router as auth_router
from datetime import timedelta  

SECRET_KEY = os.getenv("SECRET_KEY")
app = FastAPI()
templates = Jinja2Templates(directory="html")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router, prefix="/auth")
cred = credentials.Certificate("busconncet-firebase-adminsdk-3q883-4a49b71c98.json")  # 替換為服務帳戶金鑰的實際路徑
firebase_admin.initialize_app(cred)

class NotificationRequest(BaseModel):
    token: str
    title: str
    body: str

class SubscribeRequest(BaseModel):
    member_id: int
    route_name: str
    notification_time: str
    token: str
    direction: int
    neareststop: str
    client_info: str

class TokenUpdateRequest(BaseModel):
    member_id: int
    token: str
    client_info: str

class FavoriteRoute(BaseModel):
    member_id: int
    route_name: str
class RouteDeleteRequest(BaseModel):
    route_name: str


load_dotenv()


def connect_to_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

def get_current_table():
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    cursor.execute("SELECT current_table FROM table_status")
    result = cursor.fetchone()
    cursor.close()
    db_connection.close()
    return result[0] if result else "bus_estimated"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("mainpage.html", {"request": request})

@app.get("/bus", response_class=HTMLResponse)
async def bus_details(request: Request, route_name: str):
    return templates.TemplateResponse("busdetails.html", {"request": request, "route_name": route_name})
@app.get("/home", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/member", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("memberpage.html", {"request": request})


@app.get("/api/search_routename")
async def search_routename():
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    query = """
    select route_name from bus_route
    """
    cursor.execute(query)
    results = cursor.fetchall()
    return results
    
@app.get("/api/search/{route_name}")
async def search_bus(route_name: str):
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    query = """
    SELECT br.route_name, bs.start, bs.end, bs.direction, bs.stops 
    FROM bus_route br 
    JOIN bus_stop bs ON br.id = bs.route_id 
    WHERE br.route_name = %s
    """
    cursor.execute(query, (route_name,))
    results = cursor.fetchall()
    if results:
        for result in results:
            result['stops'] = json.loads(result['stops'])
        cursor.close()
        db_connection.close()
        return JSONResponse(content=results)
    else:
        cursor.close()
        db_connection.close()
        raise HTTPException(status_code=404, detail="Route not found")

@app.get("/api/search_estimate")
async def search_estimate(route_name: str):
    db_connection = None
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        current_table = get_current_table()
        query = f"""
        SELECT route_name, stop_name, direction, estimated_time, stop_status
        FROM {current_table}
        WHERE route_name = %s
        """
        cursor.execute(query, (route_name,))
        results = cursor.fetchall()

        direction_0 = [row for row in results if row['direction'] == 0]
        direction_1 = [row for row in results if row['direction'] == 1]

        return JSONResponse(content={"direction_0": direction_0, "direction_1": direction_1})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_connection:
            cursor.close()
            db_connection.close()

@app.get("/api/searchlocation")
async def search_bus(route_name: str):
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    query = """
    SELECT st.stop_name, st.position_lon, st.position_lat, st.direction
    FROM stop_location st 
    JOIN bus_route br ON br.id = st.route_id 
    WHERE br.route_name = %s
    """
    cursor.execute(query, (route_name,))
    results = cursor.fetchall()
    cursor.close()
    db_connection.close()
    return JSONResponse(content=results)

@app.post("/api/subscribe")
async def subcribe(request: SubscribeRequest):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor()
    
        query = """
        INSERT INTO user_notifications (member_id, route_name, notification_time, token, client_info, direction, neareststop)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(query, (
            request.member_id,
            request.route_name,
            request.notification_time,
            request.token,
            request.client_info,
            request.direction,
            request.neareststop
        ))
        db_connection.commit()
        return {"message": "Subscription successfully created"}
    except Exception as e:
        db_connection.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create subscription: {e}")
    finally:
        cursor.close()
        db_connection.close()

@app.post("/api/update-token")
async def update_token(request: TokenUpdateRequest):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()

    try:
        # 檢查是否存在多筆該用戶端資訊的記錄
        query_check = """
        SELECT id FROM user_notifications
        WHERE member_id = %s AND client_info = %s
        """
        cursor.execute(query_check, (request.member_id, request.client_info))
        records = cursor.fetchall()

        if records:
            # 如果存在多筆記錄，逐一更新 token
            query_update = """
            UPDATE user_notifications
            SET token = %s, created_at = NOW()
            WHERE id = %s
            """
            for record in records:
                cursor.execute(query_update, (request.token, record[0]))
            db_connection.commit()
            return {"message": f"Token updated successfully for {len(records)} record(s)"}
        else:
            # 如果不存在，直接返回，不執行任何操作
            return {"message": "No existing record found, no update performed"}

    except Exception as e:
        db_connection.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update token: {e}")
    finally:
        cursor.close()
        db_connection.close()
#我的最愛
@app.post('/api/favorite')
async def add_favorite_route(request: FavoriteRoute):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor()

        query_check = """
        SELECT id FROM favorite_routes
        WHERE member_id = %s AND route_name = %s
        """
        cursor.execute(query_check, (request.member_id, request.route_name))
        existing_favorite = cursor.fetchone()
        if existing_favorite:
            return {"success": False, "message": "這條路線已經在你的最愛中"}
        else:
            query_insert = """
            INSERT INTO favorite_routes (member_id, route_name)
            VALUES (%s, %s)
            """
            cursor.execute(query_insert, (request.member_id, request.route_name))
            db_connection.commit()
            return {"success": True, "message": "已將路線加入我的最愛"}
        
    except Exception as e:
        db_connection.rollback()
        raise HTTPException(status_code=500, detail=f"無法加入我的最愛: {e}")

    finally:
        cursor.close()
        db_connection.close()
@app.get("/api/favorites/{member_id}")
async def get_favorites(member_id: int):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        
        query = """
        SELECT route_name FROM favorite_routes WHERE member_id = %s
        """
        cursor.execute(query, (member_id,))
        favorites = cursor.fetchall()
        
        return JSONResponse(content=favorites)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取我的最愛: {e}")
    finally:
        cursor.close()
        db_connection.close()
@app.delete("/api/favorites/{member_id}")
async def delete_fav(member_id: int, request: RouteDeleteRequest):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        query ="""
            Delete from favorite_routes where member_id = %s and route_name = %s
        """
        cursor.execute(query, (member_id,request.route_name))
        db_connection.commit()
        
        return {"message": "我的最愛已成功刪除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法刪除我的最愛: {e}")
    finally:
        cursor.close()
        db_connection.close()
    
@app.post("/send-notification/")
async def send_notification(request: NotificationRequest):
    # 建立通知消息
    message = messaging.Message(
        notification=messaging.Notification(
            title=request.title,
            body=request.body,
        ),
        token=request.token,
    )  
    try:
        # 發送通知
        response = messaging.send(message)
        return {"message": "Notification sent successfully", "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {e}")
   
#獲取訂閱   
@app.get("/api/subscriptions/{member_id}")
async def get_subscriptions(member_id: int):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        
        query = """
        SELECT id, route_name, notification_time, direction, neareststop,client_info
        FROM user_notifications 
        WHERE member_id = %s
        """
        cursor.execute(query, (member_id,))
        subscriptions = cursor.fetchall()

        # 將 timedelta 轉換為字串
        for subscription in subscriptions:
            if isinstance(subscription['notification_time'], (timedelta,)):
                # 假設 notification_time 是時間間隔，需要格式化為合適的字串
                total_seconds = subscription['notification_time'].total_seconds()
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                subscription['notification_time'] = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        
        return JSONResponse(content=subscriptions)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取訂閱: {e}")
    finally:
        cursor.close()
        db_connection.close()

#取消訂閱
@app.delete("/api/subscriptions/{member_id}/{subscription_id}")
async def delete_subscription(member_id: int, subscription_id: int):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor()
        
        query = """
        DELETE FROM user_notifications 
        WHERE id = %s AND member_id = %s
        """
        cursor.execute(query, (subscription_id, member_id))
        db_connection.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="沒有找到對應的訂閱")
        
        return {"message": "訂閱已成功刪除"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法刪除訂閱: {e}")
    finally:
        cursor.close()
        db_connection.close()
#更新訂閱
@app.patch("/api/subscriptions/{member_id}/{subscription_id}")
async def update_subscription_time(member_id: int, subscription_id: int, request: dict):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor()

        # 更新訂閱時間
        query = """
        UPDATE user_notifications
        SET notification_time = %s
        WHERE id = %s AND member_id = %s
        """
        cursor.execute(query, (request['notification_time'], subscription_id, member_id))
        db_connection.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="沒有找到對應的訂閱")

        return {"message": "訂閱時間已成功更新"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法更新訂閱時間: {e}")
    finally:
        cursor.close()
        db_connection.close()

@app.get("/health")
async def health_check():
    return {"status": "ok"}