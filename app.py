import requests
import json
import fastapi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import mysql.connector
import os
from dotenv import load_dotenv

app = FastAPI()
templates = Jinja2Templates(directory="html")
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
    return templates.TemplateResponse("selectbus.html", {"request": request})

@app.get("/search/{route_name}")
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
            # 轉換為 Python 列表
            result['stops'] = json.loads(result['stops'])
        cursor.close()
        db_connection.close()
        return JSONResponse(content=results)
    else:
        cursor.close()
        db_connection.close()
        raise HTTPException(status_code=404, detail="Route not found")
    
@app.get("/search_estimate")
async def search_estimate(route_name: str):
    db_connection = None
    try:
        db_connection = connect_to_db()
        cursor = db_connection.cursor(dictionary=True)
        current_table = get_current_table()  # 獲取當前表名
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

@app.get("/health")
async def health_check():
    return {"status": "ok"}
