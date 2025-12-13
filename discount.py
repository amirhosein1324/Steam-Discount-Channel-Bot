import time
import threading
import asyncio
import re
from datetime import datetime
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from telegram.ext import Application
from telegram import Bot

URL = 'https://store.steampowered.com/search/?supportedlang=english&specials=1&ndl=1'
SCROLL_PAUSE_TIME = 2.0
SURVEILLANCE_INTERVAL = 1800
SCRAPE_TOLERANCE = 0.90
LAST_RUN_FILE = 'last_run_timestamp.txt'

BOT_TOKEN = "PASTE YOUR TELEGRAM BOT TOKEN HERE"
CHANNEL_ID = "YOUR_CHANNEL_ID_OR_USERNAME" 

bot_application = None
bot_loop = None

def get_last_run_timestamp():
    try:
        with open(LAST_RUN_FILE, 'r') as f:
            return float(f.read().strip())
    except FileNotFoundError:
        print("[Timestamp] File not found. Returning 0 (will treat all deals as new).")
        return 0.0
    except Exception as e:
        print(f"[Timestamp] Error reading file: {e}. Returning 0.")
        return 0.0

def save_last_run_timestamp(timestamp):
    try:
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(str(timestamp))
    except Exception as e:
        print(f"[Timestamp Error] Could not save timestamp: {e}")

def initialize_selenium():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    try:
        driver_path = ChromeDriverManager().install()
        driver_service = Service(driver_path)
        driver = webdriver.Chrome(service=driver_service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"[Scraper Error] Driver init failed: {e}")
        return None

def get_expected_count(driver):
    try:
        count_element = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "search_results_count"))
        )
        text = count_element.text.strip()
        match = re.search(r'([\d,]+)', text)
        if match:
            number_str = match.group(1).replace(',', '')
            return int(number_str)
    except Exception:
        pass
    return 0

def run_scraper_logic():
    driver = initialize_selenium()
    if not driver:
        return []

    print("[Scraper] Starting scan...")
    try:
        driver.get(URL)
        WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.ID, "search_resultsRows")))

        expected_total = get_expected_count(driver)
        print(f"[Scraper] Steam reports {expected_total} total discounted games available.")

        last_height = driver.execute_script("return document.body.scrollHeight")
        retries = 0
        max_scroll_retries = 5

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)

            new_height = driver.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                retries += 1
                current_count = len(driver.find_elements(By.CSS_SELECTOR, '#search_resultsRows a.search_result_row'))

                if expected_total > 0 and current_count >= (expected_total * SCRAPE_TOLERANCE):
                    print("[Scraper] Achieved target item count. Stopping scroll.")
                    break

                if retries >= max_scroll_retries:
                    print(f"[Scraper] Max scroll retries ({max_scroll_retries}) reached. Stopping scroll.")
                    break
                
                time.sleep(3)
                continue

            retries = 0
            last_height = new_height

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        sales_items = soup.select('#search_resultsRows a.search_result_row')

        scraped_count = len(sales_items)
        print(f"[Scraper] Physically scraped {scraped_count} items.")

        if expected_total > 0 and scraped_count < (expected_total * SCRAPE_TOLERANCE):
            print(f"🚨 [SAFETY ABORT] Scrape incomplete! Expected ~{expected_total}, but found {scraped_count}.")
            return []

        scraped_data = []
        for item in sales_items:
            try:
                name_element = item.select_one('.title')
                game_name = name_element.text.strip() if name_element else "Unknown Game"
                steam_link = item.get('href', 'N/A')

                scraped_data.append({
                    'name': game_name,
                    'steam_link': steam_link
                })
            except Exception as item_e:
                print(f"[Scraper Error] Failed to process item: {item_e}")
                continue

        return scraped_data

    except Exception as e:
        print(f"[Scraper Critical Error] General scraper failure: {e}")
        return []
    finally:
        if driver:
            driver.quit()

async def post_to_channel(game_list, is_random=False):
    if not bot_application or not CHANNEL_ID:
        print("[Alert] Channel posting skipped: Bot or Channel ID not configured.")
        return

    bot: Bot = bot_application.bot
    
    if not game_list:
        if not is_random:
            print("[Alert] No new games to post to channel.")
        return

    if not is_random:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"🚨 <b>Steam Specials Alert:</b> Found {len(game_list)} NEW game(s) on sale! 🥳",
            parse_mode='HTML'
        )

    for i, game in enumerate(game_list):
        name = game['name']
        link = game['steam_link']
        
        prefix = f"🎲 {i+1}. " if is_random else "🔥 NEW DEAL! "
        
        msg = (f"{prefix}<b>{name}</b>\n"
               f"🔗 {link}")
        
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode='HTML')
            if not is_random:
                await asyncio.sleep(10) 
        except Exception as e:
            print(f"Failed to send game alert to channel {CHANNEL_ID} for {name}: {e}")

def surveillance_loop():
    print("--- Surveillance System Started ---")
    while True:
        current_run_timestamp = time.time()
        
        data = run_scraper_logic()

        if data:
            last_run_time = get_last_run_timestamp()
            new_arrivals = []
            
            if last_run_time == 0.0:
                import random
                random_games = random.sample(data, min(5, len(data)))
                print(f"[Alert] First run detected. Posting 5 random deals.")
                asyncio.run_coroutine_threadsafe(
                    post_to_channel(random_games, is_random=True),
                    bot_loop
                )
                new_arrivals = data
                
            else:
                if current_run_timestamp - last_run_time > 7200: 
                     new_arrivals = data
                     print(f"[Alert] Catch-up mode: Sending {len(new_arrivals)} deals from downtime.")
                else:
                    new_arrivals = data[:10]
                    
            
            if new_arrivals:
                if bot_application and bot_loop:
                    asyncio.run_coroutine_threadsafe(
                        post_to_channel(new_arrivals, is_random=False),
                        bot_loop
                    )
                    
            save_last_run_timestamp(current_run_timestamp)

            print(f"[Surveillance] Sleeping for {SURVEILLANCE_INTERVAL} seconds...")
            time.sleep(SURVEILLANCE_INTERVAL)
        else:
            print("[Surveillance] Scrape failed or aborted. Retrying in 60 seconds...")
            time.sleep(60)
            continue

async def start_and_init(application: Application):
    global bot_loop
    bot_loop = asyncio.get_running_loop()
    print("[Bot] Event loop captured for background alerts.")

    if CHANNEL_ID and bot_application:
        try:
            await bot_application.bot.send_message(
                chat_id=CHANNEL_ID,
                text="🤖 **Steam Discount Bot has just started/restarted.**\n"
                     "Surveillance mode is active. New deals will be posted here.",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"[Startup Error] Failed to send startup message to channel: {e}")

if __name__ == '__main__':
    if BOT_TOKEN == "PASTE YOUR TELEGRAM BOT TOKEN HERE" or CHANNEL_ID == "YOUR_CHANNEL_ID_OR_USERNAME":
        print("ERROR: You must edit the file and insert your Telegram Bot Token AND Channel ID!")
    else:
        print("--- Bot Starting ---")

        bot_application = Application.builder().token(BOT_TOKEN).post_init(start_and_init).build()

        scraper_thread = threading.Thread(target=surveillance_loop, daemon=True)
        scraper_thread.start()

        bot_application.run_polling()