import requests
from datetime import datetime
import random
import logging
import sqlite3
import time
import threading


TELEGRAM_TOKEN = "YOUR TELEGRAM BOT TOKEN"
CHANNEL_USERNAME = "@YOUR_CHANNEL_USERNAME"
CHANNEL_LINK = "YOUR CHANNEL USERNAME WITHOUT @"
DB_FILE = "steam.db"
CHEAPSHARK_URL = "https://www.cheapshark.com/api/1.0/deals"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def get_conn(self):
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._local.conn

    def _init_db(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS deals (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, normalPrice REAL, salePrice REAL, savings REAL, url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS times (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT UNIQUE)")
        c.execute("CREATE TABLE IF NOT EXISTS wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, game_name TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS all_games (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, normalPrice REAL, salePrice REAL, savings REAL, url TEXT)")
        conn.commit()

    def query(self, sql, params=(), commit=False, fetch=False):
        conn = self.get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            if commit: conn.commit()
            if fetch: return cursor.fetchall()
            return cursor
        except Exception as e:
            logging.error(f"SQL Error: {e} | Query: {sql}")
            return None
db = DatabaseManager(DB_FILE)

def send_telegram(chat_id, text, is_channel=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": not is_channel
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

def check_wishlist_loop():
    while True:
        time.sleep(60)
        items = db.query("SELECT id, chat_id, game_name FROM wishlist", fetch=True)
        if not items: continue

        for row_id, chat_id, game_name in items:
            matches = db.query("SELECT title, salePrice , normalPrice , savings , url FROM deals WHERE title LIKE ?", (f"%{game_name}%",), fetch=True)
            for m in matches:
                msg = (
                    "🎯 <b>Wishlist Match Found!</b>\n"
                    f"🎮 {m[0]}\n"
                    f"💰 Sale: ${m[1]}\n"
                    f"💵 Normal: ${m[2]}\n"
                    f"🔥 Savings: {m[3]}%\n"
                    f"🔗 <a href='{m[4]}'>View on Steam website</a>"
                )
                send_telegram(chat_id, msg)
                db.query("DELETE FROM wishlist WHERE id = ?", (row_id,), commit=True)
                logging.info(f"Notified {chat_id} about {m[0]}")

def get_all_games():
    """Syncs the complete game list from SteamSpy."""
    logging.info("Starting SteamSpy Full Sync...")
    page = 0
    while page < 5:  
        url = f"https://steamspy.com/api.php?request=all&page={page}"
        try:
            res = requests.get(url, timeout=20)
            data = res.json()
            if not data: break
            
            for appid, info in data.items():
                if int(info.get('discount', 0)) > 0:
                    title = info.get('name')
                    normal = int(info.get('initialprice', 0)) / 100
                    sale = int(info.get('price', 0)) / 100
                    savings = info.get('discount')
                    link = f"https://store.steampowered.com/app/{appid}"
                    
                    db.query("""INSERT INTO all_games (title, normalPrice, salePrice, savings, url) 
                             VALUES (?, ?, ?, ?, ?)""", (title, normal, sale, savings, link), commit=True)
            logging.info(f"Page {page} synced.")
            page += 1
            time.sleep(2) 
        except Exception as e:
            logging.error(f"SteamSpy Error: {e}")
            break


    db.query("""DELETE FROM all_games WHERE rowid NOT IN (SELECT MAX(rowid) FROM all_games GROUP BY title)""", commit=True)

def search_game(chat_id, word):
    rows = db.query("SELECT title, normalPrice, salePrice, savings, url FROM all_games WHERE title LIKE ?", (f"%{word}%",), fetch=True)
    if not rows:
        send_telegram(chat_id, f"❌ No active discounts found for '{word}'. Added to wishlist! 🔔")
        db.query("INSERT INTO wishlist (chat_id, game_name) VALUES (?, ?)", (chat_id, word), commit=True)
        return

    for r in rows[:5]: 
        msg = (
            "🔍 <b>Search Result:</b>\n"
            f"🎮 {r[0]}\n"
            f"💰 Sale: ${r[2]}\n"
            f"💵 Normal: ${r[1]}\n"
            f"🔥 Discount: {r[3]}%\n"
            f"🔗 <a href='{r[4]}'>Link</a>"
        )
        send_telegram(chat_id, msg)

def telegram_bot_worker():
    last_id = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": (last_id + 1) if last_id else None, "timeout": 20}
        try:
            res = requests.get(url, params=params, timeout=25).json()
            if not res.get("ok"): continue

            for update in res.get("result", []):
                last_id = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id: continue

                if text == "/start":
                    db.query("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (str(chat_id),), commit=True)
                    send_telegram(chat_id, f"👋 Welcome! I track Steam deals.\nJoin @{CHANNEL_LINK} for live updates.")
                elif text.startswith("/search "):
                    query_word = text.split(" ", 1)[1].strip()
                    search_game(chat_id, query_word)
                elif text == "/help":
                    send_telegram(chat_id, "📌 <b>Commands:</b>\n/ search  [name] - Find a game\n/end_notification - Clear wishlist")
                elif text == "/end_notification":
                    db.query("DELETE FROM wishlist WHERE chat_id = ?", (str(chat_id),), commit=True)
                    send_telegram(chat_id, "🔇 Wishlist cleared.")
        except Exception as e:
            logging.error(f"Bot Update Error: {e}")
        time.sleep(1)

def deals_tracker_worker():
    while True:
        try:
            time_row = db.query("SELECT time FROM times ORDER BY id DESC LIMIT 1", fetch=True)
            last_saved = time_row[0][0] if time_row else 0
            
            res = requests.get(CHEAPSHARK_URL, params={"sortBy": "Recent", "pageSize": 30, "storeID": 1}, timeout=15)
            deals = res.json()
            
            new_timestamp = last_saved
            for deal in deals:
                change_ts = int(deal.get("lastChange", 0))
                if change_ts > last_saved:
                    title = deal["title"]
                    sale = deal["salePrice"]
                    normal = deal["normalPrice"]
                    save = deal["savings"][:4]
                    url = f"https://store.steampowered.com/app/{deal['steamAppID']}"
                    
                    msg = f"🎮 <b>{title}</b>\n💰 Sale: ${sale}\n🔥 Discount: {save}%\n🔗 <a href='{url}'>View Deal</a>"
                    send_telegram(CHANNEL_USERNAME, msg, is_channel=True)
                    
                    db.query("INSERT INTO deals (title, normalPrice, salePrice, savings, url) VALUES (?,?,?,?,?)",
                             (title, normal, sale, save, url), commit=True)
                    
                    if change_ts > new_timestamp:
                        new_timestamp = change_ts
            
            if new_timestamp > last_saved:
                db.query("INSERT INTO times (time) VALUES (?)", (new_timestamp,), commit=True)
            
        except Exception as e:
            logging.error(f"Deals Tracker Error: {e}")
        
        time.sleep(300)

if __name__ == "__main__":
    get_all_games()
    
    threads = [
        threading.Thread(target=telegram_bot_worker, daemon=True),
        threading.Thread(target=deals_tracker_worker, daemon=True),
        threading.Thread(target=check_wishlist_loop, daemon=True),
        threading.Thread(target=lambda: (time.sleep(1800), get_all_games()) , daemon=True) 
    ]
    
    for t in threads: t.start()
    
    logging.info("All systems Active")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")