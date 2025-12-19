import requests
from datetime import datetime
import sqlite3
import time
import threading
import random

BOT_TOKEN = "TELEGRAM bot TOKEN"
CHANNEL_ID = "PASTE YOUR CHANNEL USERNAME HERE"
CHANNEL_ALIAS = "PASTE YOUR CHANNEL NAME HERE"
DB_NAME = "steam_deals.db"

DEAL_PARAMS = {
    "sortBy": "Recent",
    "pageSize": 50,
    "pageNumber": 0,
    "storeID": 1
}
CHEAPSHARK_URL = "https://www.cheapshark.com/api/1.0/deals"

def initialize_database():
    connection = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = connection.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        normalPrice REAL,
        salePrice REAL,
        savings REAL,
        url TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS all_games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        normalPrice REAL,
        salePrice REAL,
        savings REAL,
        url TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS update_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER
    )
    """)
    connection.commit()
    return connection, cursor

db_conn, db_cursor = initialize_database()
last_processed_id = None

def broadcast_to_channel(message):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(api_url, data=payload, timeout=12)
        if response.status_code == 200:
            print(f"Broadcast success: {message[:30]}...")
    except requests.exceptions.RequestException:
        print("Connectivity issue: Unable to reach Telegram API.")

def notify_user(chat_id, message):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(api_url, data=payload)

def search_game(chat_id, query):
    results = db_cursor.execute("""
        SELECT title, normalPrice, salePrice, savings, url
        FROM all_games
        WHERE title LIKE ?
    """, (f"%{query}%",)).fetchall()

    if not results:
        notify_user(chat_id, "No matching deals found in our database.")
        return

    for item in results:
        title, n_price, s_price, disc, link = item
        response_msg = (
            "Match Found:\n"
            f"Game: {title}\n"
            f"Current: {s_price}$\n"
            f"Original: {n_price}$\n"
            f"Off: {disc}%\n"
            f"Link: {link}"
        )
        notify_user(chat_id, response_msg)

def fetch_steamspy_data():
    db_cursor.execute("DROP TABLE IF EXISTS all_games;")
    db_cursor.execute("""
    CREATE TABLE all_games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        normalPrice REAL,
        salePrice REAL,
        savings REAL,
        url TEXT
    )
    """)
    
    page = 0
    while True:
        api_url = f"https://steamspy.com/api.php?request=all&page={page}"
        try:
            res = requests.get(api_url, timeout=15)
            if len(res.text) < 100: break
            
            data = res.json()
            for entry in data:
                game = data[entry]
                if int(game["discount"]) > 0:
                    db_cursor.execute("""
                        INSERT INTO all_games (title, normalPrice, salePrice, savings, url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        game["name"], 
                        int(game["initialprice"])/100, 
                        int(game["price"])/100, 
                        game["discount"], 
                        f"https://store.steampowered.com/app/{game['appid']}"
                    ))
            db_conn.commit()
            print(f"Synced Page {page}")
            page += 1
        except Exception as e:
            print(f"Sync Error on page {page}: {e}")
            time.sleep(2)

def monitor_telegram_updates():
    global last_processed_id
    poll_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    while True:
        try:
            params = {"timeout": 5, "offset": (last_processed_id + 1) if last_processed_id else None}
            response = requests.get(poll_url, params=params).json()

            if not response.get("ok"): continue

            for update in response["result"]:
                last_processed_id = update["update_id"]
                if "message" not in update: continue

                msg_data = update["message"]
                user_id = msg_data["chat"]["id"]
                cmd_text = msg_data.get("text", "")

                if cmd_text == "/start":
                    welcome = (
                        "Steam Tracker Active\n\n"
                        "I monitor price drops and notify you instantly.\n"
                        f"Join: @{CHANNEL_ALIAS}\n\n"
                        "Try /search [game name]"
                    )
                    notify_user(user_id, welcome)

                elif cmd_text.startswith("/search "):
                    term = cmd_text.split(" ", 1)[1].strip()
                    search_game(user_id, term)

                elif cmd_text == "/help":
                    help_msg = "Available Commands:\n/search - Find deals\n/start - Info"
                    notify_user(user_id, help_msg)

        except Exception as error:
            print(f"Polling Error: {error}")
        time.sleep(0.5)

def check_new_deals():
    while True:
        print("Scanning for price drops...")
        try:
            pass 
        except Exception as e:
            print(f"Deal Scanner Error: {e}")
        time.sleep(70)

if __name__ == "__main__":
    print("Steam Bot System Initialized")
    
    tg_thread = threading.Thread(target=monitor_telegram_updates, daemon=True)
    tg_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down safely.")