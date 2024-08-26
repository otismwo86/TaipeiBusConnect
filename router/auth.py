# router/auth.py
from fastapi import *
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
import jwt
import mysql.connector
import datetime
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse,RedirectResponse
from mysql.connector import errors
import bcrypt


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
templates = Jinja2Templates(directory="html")


class LoginRequest(BaseModel):
    user_id: int
    name: str
    email: str

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)
SECRET_KEY = os.getenv("SECRET_KEY")

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
    
    except errors.IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    except errors.Error as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_jwt_token(token)
        return {"status": "success", "message": "Token is valid", "user_id": payload["sub"], "user_name":payload["name"]}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)