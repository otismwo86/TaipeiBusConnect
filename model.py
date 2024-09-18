import mysql.connector
import os
from dotenv import load_dotenv
from datetime import timedelta
import json

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

def fetch_routes_from_db():
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    cursor.execute("SELECT route_name FROM bus_route")
    results = cursor.fetchall()
    cursor.close()
    db_connection.close()
    return results

def fetch_bus_route_details(route_name):
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
    cursor.close()
    db_connection.close()
    return results

def fetch_bus_estimates(route_name):
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
    cursor.close()
    db_connection.close()
    return results

def fetch_stop_locations(route_name):
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
    return results

def insert_subscription(subscription_data):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    query = """
    INSERT INTO user_notifications (member_id, route_name, notification_time, token, client_info, direction, neareststop)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.execute(query, (
            subscription_data.member_id,
            subscription_data.route_name,
            subscription_data.notification_time,
            subscription_data.token,
            subscription_data.client_info,
            subscription_data.direction,
            subscription_data.neareststop
        ))
        db_connection.commit()
        return True
    except Exception as e:
        db_connection.rollback()
        raise e
    finally:
        cursor.close()
        db_connection.close()

def update_token(member_id, token, client_info):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query_check = """
        SELECT id FROM user_notifications
        WHERE member_id = %s AND client_info = %s
        """
        cursor.execute(query_check, (member_id, client_info))
        records = cursor.fetchall()

        if records:
            query_update = """
            UPDATE user_notifications
            SET token = %s, created_at = NOW()
            WHERE id = %s
            """
            for record in records:
                cursor.execute(query_update, (token, record[0]))
            db_connection.commit()
            return len(records)
        else:
            return 0
    except Exception as e:
        db_connection.rollback()
        raise e
    finally:
        cursor.close()
        db_connection.close()

def add_favorite_route(member_id, route_name):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query_check = """
        SELECT id FROM favorite_routes
        WHERE member_id = %s AND route_name = %s
        """
        cursor.execute(query_check, (member_id, route_name))
        existing_favorite = cursor.fetchone()
        if existing_favorite:
            return False
        else:
            query_insert = """
            INSERT INTO favorite_routes (member_id, route_name)
            VALUES (%s, %s)
            """
            cursor.execute(query_insert, (member_id, route_name))
            db_connection.commit()
            return True
    except Exception as e:
        db_connection.rollback()
        raise e
    finally:
        cursor.close()
        db_connection.close()

def get_favorites(member_id):
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    try:
        query = """
        SELECT route_name FROM favorite_routes WHERE member_id = %s
        """
        cursor.execute(query, (member_id,))
        favorites = cursor.fetchall()
        return favorites
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()

def get_subscriptions(member_id):
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    try:
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
        return subscriptions
    
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()
def fetch_subscription(member_id: int, route_name: str):
    db_connection = connect_to_db()
    cursor = db_connection.cursor(dictionary=True)
    try:
        query = """
        SELECT id, notification_time, direction, neareststop 
        FROM user_notifications 
        WHERE member_id = %s AND route_name = %s
        """
        cursor.execute(query, (member_id, route_name))
        subscription = cursor.fetchone()

        if subscription and isinstance(subscription['notification_time'], (timedelta,)):
            total_seconds = subscription['notification_time'].total_seconds()
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            subscription['notification_time'] = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        
        return subscription
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()
        
def delete_favorite_route(member_id, route_name):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query = """
        DELETE FROM favorite_routes WHERE member_id = %s AND route_name = %s
        """
        cursor.execute(query, (member_id, route_name))
        db_connection.commit()
        return cursor.rowcount > 0
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()

def delete_subscription(member_id, subscription_id):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query = """
        DELETE FROM user_notifications 
        WHERE id = %s AND member_id = %s
        """
        cursor.execute(query, (subscription_id, member_id))
        db_connection.commit()
        return cursor.rowcount > 0
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()

def update_subscription_time(member_id, subscription_id, new_time):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query = """
        UPDATE user_notifications
        SET notification_time = %s
        WHERE id = %s AND member_id = %s
        """
        cursor.execute(query, (new_time, subscription_id, member_id))
        db_connection.commit()
        return cursor.rowcount > 0
    except Exception as e:
        db_connection.rollback()
        raise e
    finally:
        cursor.close()
        db_connection.close()

def save_chat_message(route_name, user_name, message, image_url, timestamp):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query = """
        INSERT INTO chat_messages (route_name, user_name, message, image_url, timestamp)
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (route_name, user_name, message, image_url, timestamp))
        db_connection.commit()
    except Exception as e:
        db_connection.rollback()
        raise e
    finally:
        cursor.close()
        db_connection.close()

def load_chat_history(route_name):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        query = """
        SELECT user_name, message, image_url, timestamp 
        FROM chat_messages 
        WHERE route_name = %s 
        ORDER BY timestamp ASC
        """
        cursor.execute(query, (route_name,))
        messages = cursor.fetchall()
        return [{"sender": msg[0], "content": msg[1], "image_url": msg[2], "timestamp": msg[3].strftime("%Y-%m-%d %H:%M:%S")} for msg in messages]
    except Exception as e:
        raise e
    finally:
        cursor.close()
        db_connection.close()
