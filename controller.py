# controllers.py
from fastapi import *
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from view import (
    render_main_page, render_bus_details_page, render_member_page,
    render_test_notification_page, render_chatroom_page,
    render_favorites_page, render_subscription_page, render_upload_page
)
from model import (
    fetch_routes_from_db, fetch_bus_route_details, fetch_bus_estimates, 
    fetch_stop_locations, insert_subscription, update_token,
    add_favorite_route, get_favorites, delete_favorite_route, 
    delete_subscription, update_subscription_time, save_chat_message,
    load_chat_history,connect_to_db,get_subscriptions,fetch_subscription
)
from pydantic import BaseModel
import bcrypt
import os
import json
import jwt
from datetime import datetime, timedelta, timezone
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
import firebase_admin
from firebase_admin import credentials, messaging
from typing import List, Dict, Optional
import redis

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
#設定Redis連接
#redis_client = redis.Redis(host='redis', port=6379, db=0) #部屬用
redis_client = redis.Redis(host='localhost', port=6379, db=0) #本地用
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
AWS_BUCKET_NAME = 'myotiss3demo'
cred = credentials.Certificate("busconncet-firebase-adminsdk-3q883-4a49b71c98.json")  #替換為服務帳戶金鑰的實際路徑
firebase_admin.initialize_app(cred)
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

# 定義數據模型
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

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, route_name: str):
        await websocket.accept()
        if route_name not in self.active_connections:
            self.active_connections[route_name] = []
        self.active_connections[route_name].append(websocket)

        chat_history = self.load_chat_history_from_db(route_name)
        for message in chat_history:
            await websocket.send_text(json.dumps(message))

    def disconnect(self, websocket: WebSocket, route_name: str):
        if route_name in self.active_connections:
            self.active_connections[route_name].remove(websocket)

    async def broadcast(self, message: str, route_name: str, user_name: str = None, image_url: str = None, save_to_db: bool = True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {
            "sender": user_name,
            "content": message,
            "timestamp": timestamp,
            "image_url": image_url 
        }
        if save_to_db:
            self.save_message_to_db(message, route_name, user_name, timestamp, image_url)

        if route_name in self.active_connections:
            for connection in self.active_connections[route_name]:
                await connection.send_text(json.dumps(message_data))

    def save_message_to_db(self, message: str, route_name: str, user_name: str, timestamp: str, image_url: str = None):
        db = connect_to_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO chat_messages (route_name, user_name, message, image_url, timestamp) VALUES (%s, %s, %s, %s, %s)", 
                       (route_name, user_name, message, image_url, timestamp))
        db.commit()
        cursor.close()
        db.close()

    def load_chat_history_from_db(self, route_name: str):
        db = connect_to_db()
        cursor = db.cursor()
        cursor.execute("SELECT user_name, message, image_url, timestamp FROM chat_messages WHERE route_name = %s ORDER BY timestamp ASC", (route_name,))
        messages = cursor.fetchall()
        cursor.close()
        db.close()
        return [{"sender": msg[0], "content": msg[1], "image_url": msg[2], "timestamp": msg[3].strftime("%Y-%m-%d %H:%M:%S")} for msg in messages]

    async def upload_file(self, file: UploadFile, message: str, route_name: str, user_name: str):
        try:
            unique_filename = f"{uuid.uuid4()}_{file.filename}"
            s3_client.upload_fileobj(file.file, AWS_BUCKET_NAME, unique_filename)
            cloudfront_url = f"https://d2h11xp6qwlofm.cloudfront.net/{unique_filename}"
            
            await self.broadcast(message=message, route_name=route_name, user_name=user_name, image_url=cloudfront_url)
            return {"message": "File uploaded and broadcasted successfully", "image_url": cloudfront_url}
        except NoCredentialsError:
            return {"error": "Credentials not available"}
        
manager = ConnectionManager()
# JWT token 相關操作
def create_jwt_token(user_id: int, name: str, email: str):
    to_encode = {"sub": user_id, "name": name, "email": email}
    expire = datetime.now(timezone.utc) + timedelta(days=3)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

# 路由處理
@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render_main_page(request)

@router.get("/bus", response_class=HTMLResponse)
async def bus_details(request: Request, route_name: str):
    return render_bus_details_page(request, route_name)

@router.get("/home", response_class=HTMLResponse)
async def read_home(request: Request):
    return render_test_notification_page(request)

@router.get("/member", response_class=HTMLResponse)
async def member_page(request: Request):
    return render_member_page(request)

@router.get("/api/search_routename")
async def search_routename():
    try:
        # 先從 Redis 快取中查詢
        cached_routes = redis_client.get('routes')
        if cached_routes:
            print("從 Redis 快取中獲取數據")
            # 更新快取的到期時間
            redis_client.expire('routes', 604800)
            return JSONResponse(content=json.loads(cached_routes))

        # 如果快取中沒有，從資料庫中查詢
        routes = fetch_routes_from_db()  
        redis_client.setex('routes', 604800, json.dumps(routes))  # 設定Redis快取
        print("從資料庫中查詢數據並存入 Redis 快取")
        return JSONResponse(content=routes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法查詢路線名稱: {e}")

@router.get("/api/search/{route_name}")
async def search_bus(route_name: str):
    try:
        results = fetch_bus_route_details(route_name)
        if results:
            for result in results:
                result['stops'] = json.loads(result['stops'])
            return JSONResponse(content=results)
        else:
            raise HTTPException(status_code=404, detail="Route not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法查詢路線: {e}")

@router.get("/api/search_estimate")
async def search_estimate(route_name: str):
    try:
        estimates = fetch_bus_estimates(route_name)
        direction_0 = [row for row in estimates if row['direction'] == 0]
        direction_1 = [row for row in estimates if row['direction'] == 1]
        return JSONResponse(content={"direction_0": direction_0, "direction_1": direction_1})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/searchlocation")
async def search_location(route_name: str):
    try:
        locations = fetch_stop_locations(route_name)
        return JSONResponse(content=locations)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取站點信息: {e}")

@router.post("/api/subscribe")
async def subscribe(request: SubscribeRequest):
    try:
        success = insert_subscription(request)
        if success:
            return {"message": "Subscription successfully created"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create subscription")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法創建訂閱: {e}")
    


@router.post("/api/update-token")
async def update_token_endpoint(request: TokenUpdateRequest):
    try:
        count = update_token(request.member_id, request.token, request.client_info)
        if count > 0:
            return {"message": f"Token updated successfully for {count} record(s)"}
        else:
            return {"message": "No existing record found, no update performed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法更新token: {e}")

@router.post("/api/favorite")
async def add_favorite_route_endpoint(request: FavoriteRoute):
    try:
        success = add_favorite_route(request.member_id, request.route_name)
        if success:
            return {"success": True, "message": "已將路線加入我的最愛"}
        else:
            return {"success": False, "message": "這條路線已經在你的最愛中"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法加入我的最愛: {e}")

@router.get("/api/favorites/{member_id}")
async def get_favorites_endpoint(member_id: int):
    try:
        favorites = get_favorites(member_id)
        return JSONResponse(content=favorites)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取我的最愛: {e}")
    
@router.get("/api/subscriptions/{member_id}")
async def get_subscriptions_endpoint(member_id: int):
    try:
        subscriptions = get_subscriptions(member_id)      
        return JSONResponse(content=subscriptions)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取訂閱: {e}")

@router.delete("/api/favorites/{member_id}")
async def delete_favorite_route_endpoint(member_id: int, request: RouteDeleteRequest):
    try:
        success = delete_favorite_route(member_id, request.route_name)
        if success:
            return {"message": "我的最愛已成功刪除"}
        else:
            raise HTTPException(status_code=404, detail="未找到對應的最愛路線")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法刪除我的最愛: {e}")

@router.post("/send-notification/")
async def send_notification(request: NotificationRequest):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=request.title,
                body=request.body,
            ),
            token=request.token,
        )
        response = messaging.send(message)
        return {"message": "Notification sent successfully", "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {e}")

@router.get("/buschatroom", response_class=HTMLResponse)
async def chatroom_page(request: Request, route_name: str):
    return render_chatroom_page(request, route_name)

@router.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, token: str = Query(...), route_name: str = Query(...)):
    print(f"Received token: {token} for route: {route_name}")
    try:
        # 解碼 JWT token 獲取用戶信息
        payload = decode_jwt_token(token)
        user_id = payload.get("sub")
        user_name = payload.get("name")

        # 如果驗證成功，繼續連接處理
        await manager.connect(websocket, route_name)  # 傳入 route_name
        await manager.broadcast(f"{user_name}加入了聊天室", route_name, user_name=user_name, save_to_db=False)  # 用戶加入時不存入DB

        try:
            while True:
                # 接收用戶發送的消息
                data = await websocket.receive_text()
                # 廣播帶有用戶名和路線的消息給所有在同一路線聊天室的用戶
                await manager.broadcast(data, route_name, user_name=user_name)
        except WebSocketDisconnect:
            manager.disconnect(websocket, route_name)  # 傳入 route_name
            await manager.broadcast(f"{user_name}離開了聊天室", route_name, user_name=user_name, save_to_db=False)  # 用戶離開時不存入DB
    except HTTPException as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@router.post("/upload")
async def upload_file(file: Optional[UploadFile] = File(None), message: str = Form(...), route_name: str = Form(...), user_name: str = Form(...) ):
    try:
        image_url = None
        if file:
            unique_filename = f"{uuid.uuid4()}_{file.filename}"
            s3_client.upload_fileobj(file.file, AWS_BUCKET_NAME, unique_filename)
            image_url = f"https://d2h11xp6qwlofm.cloudfront.net/{unique_filename}"

        await manager.broadcast(message=message, route_name=route_name, user_name=user_name, image_url=image_url)
        return {"message": "File uploaded and broadcasted successfully", "image_url": image_url}
    except NoCredentialsError:
        return {"error": "Credentials not available"}
    
@router.get("/api/check_subscription") #注意
async def check_subscription(member_id: int, route_name: str):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        
        query = """
        SELECT id, notification_time, direction, neareststop 
        FROM user_notifications 
        WHERE member_id = %s AND route_name = %s
        """

        cursor.execute(query, (member_id,route_name))
        subscription = cursor.fetchone()

        if subscription:
            if isinstance(subscription['notification_time'], (timedelta,)):
                total_seconds = subscription['notification_time'].total_seconds()
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                subscription['notification_time'] = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        
            return {"subscribed": True, "subscription": subscription}
        else:
            return {"subscribed": False}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取訂閱: {e}")
    finally:
        cursor.close()
        db_connection.close()
    
@router.delete("/api/subscriptions/{member_id}/{subscription_id}")#注意
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

@router.patch("/api/subscriptions/{member_id}/{subscription_id}") #注意
async def update_subscription_time(member_id: int, subscription_id: int, request: dict):
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor()

        query = """
        UPDATE user_notifications
        SET notification_time = %s
        WHERE id = %s AND member_id = %s
        """
        # 使用request['notification_time']直接從字典中獲取值
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
    
@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = connect_to_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM memberinfo WHERE email = %s", (form_data.username,))
    user = cursor.fetchone()
    cursor.close()
    db.close()

    if user is None or not bcrypt.checkpw(form_data.password.encode('utf-8'), user["password"].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_jwt_token(user["id"], user["name"], form_data.username)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/register")
async def register(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    try:
        db = connect_to_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM memberinfo WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            cursor.close()
            db.close()
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("INSERT INTO memberinfo (name, email, password) VALUES (%s, %s, %s)", (name, email, hashed_password))
        db.commit()
        cursor.close()
        db.close()
        return {"message": "User registered successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_jwt_token(token)
        return {"status": "success", "message": "Token is valid", "user_id": payload["sub"], "user_name": payload["name"]}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.get("/health")
async def health_check():
    return {"status": "ok"}
