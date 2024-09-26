import json
import fastapi
from fastapi import *
from fastapi.responses import JSONResponse, HTMLResponse,RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
import mysql.connector
from mysql.connector import errors
import os
import bcrypt
from dotenv import load_dotenv
from typing import List, Dict, Optional
import firebase_admin
from firebase_admin import credentials, messaging
from pydantic import BaseModel
from router.auth import router as auth_router
from datetime import timedelta, datetime ,timezone
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
import jwt
import redis
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware


SECRET_KEY = os.getenv("SECRET_KEY")
app = FastAPI()
templates = Jinja2Templates(directory="html")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app.mount("/static", StaticFiles(directory="static"), name="static")
cred = credentials.Certificate("busconncet-firebase-adminsdk-3q883-4a49b71c98.json")  #替換為服務帳戶金鑰的實際路徑
firebase_admin.initialize_app(cred)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
#設定Redis連接
redis_client = redis.Redis(host='redis', port=6379, db=0) #部屬用
# redis_client = redis.Redis(host='localhost', port=6379, db=0) #本地用
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
    return templates.TemplateResponse("testnoti.html", {"request": request})

@app.get("/member", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("memberpage.html", {"request": request})


@app.get("/api/search_routename")
async def search_routename():
    cached_routes = redis_client.get('routes')
    if cached_routes:
        print("從 Redis 快取中獲取數據")

        redis_client.expire('routes', 604800)

        return json.loads(cached_routes)
    
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    query = """
    SELECT route_name FROM bus_route
    """
    cursor.execute(query)
    results = cursor.fetchall()

    redis_client.setex('routes', 604800, json.dumps(results))

    print("從資料庫中查詢數據並存入 Redis 快取")
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
        query_check = """
        SELECT id FROM user_notifications
        WHERE member_id = %s AND client_info = %s
        """
        cursor.execute(query_check, (request.member_id, request.client_info))
        records = cursor.fetchall()

        if records:
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
    #建立通知消息
    message = messaging.Message(
        notification=messaging.Notification(
            title=request.title,
            body=request.body,
        ),
        token=request.token,
    )  
    try:
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

        for subscription in subscriptions:
            if isinstance(subscription['notification_time'], (timedelta,)):
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
        
#獲取route訂閱
@app.get("/api/check_subscription")
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
#登入
@app.post("/login")
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

@app.post("/register")
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
    
    except errors.IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    except errors.Error as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_jwt_token(token)
        return {"status": "success", "message": "Token is valid", "user_id": payload["sub"], "user_name":payload["name"]}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    
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

@app.get("/buschatroom", response_class=HTMLResponse)
async def read_index(request: Request, route_name: str):
    return templates.TemplateResponse("chatroom.html", {"request": request,"route_name": route_name})

@app.websocket("/ws/chat")
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

AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
AWS_BUCKET_NAME = 'myotiss3demo'

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)
#上傳圖片
@app.post("/upload")
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
         
@app.get("/health")
async def health_check():
    return {"status": "ok"}



client_id = os.getenv("GOOGLE_CLIENT_ID")
client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

# 初始化 OAuth 客戶端
oauth = OAuth()
oauth.register(
    name='google',
    client_id=client_id,
    client_secret=client_secret,
    # redirect_uri='http://127.0.0.1:8000/auth/google/callback',
    redirect_uri = 'https://otusyo.xyz/auth/google/callback',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@app.get("/auth/google")
async def google_login(request: Request):
    # redirect_uri = 'http://127.0.0.1:8000/auth/google/callback'
    redirect_uri = 'https://otusyo.xyz/auth/google/callback'
    return await oauth.google.authorize_redirect(request, redirect_uri, scope="openid email profile")
    
#google登入
@app.get("/auth/google/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    
    if 'userinfo' not in token:
        return {"error": "Failed to retrieve userinfo"}

    user_info = token['userinfo']
    
    email = user_info.get('email')
    name = user_info.get('name')

    if not email or not name:
        return {"error": "Failed to extract user information"}
    
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM memberinfo WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO memberinfo (name, email) VALUES (%s, %s)", (name, email))
        db_connection.commit()
        cursor.execute("SELECT * FROM memberinfo WHERE email = %s", (email,))
        user = cursor.fetchone()

    token = create_jwt_token(user_id=user["id"], name=name, email=email)

    # redirect_url = f"http://127.0.0.1:8000?access_token={token}"
    redirect_url = f"https://otusyo.xyz?access_token={token}"
    return RedirectResponse(url=redirect_url)

