# Steam Discount Channel Bot

A powerful Telegram bot that automatically tracks and posts Steam discount deals to a Telegram channel, lets users search for specific titles, and manage personalized wishlists.  
Perfect for gaming communities and individuals who want to keep up-to-date with the latest Steam game sales in real time!

---
## Features

- **Automated Steam sale tracking:** Pulls recent deals using [CheapShark API](https://www.cheapshark.com) and posts to your Telegram channel automatically.
- **Search support:** Users can search for discounted games by keyword with the `/search` command.
- **Wishlist Notifications:** If a user's searched game isn't on sale, it's added to their wishlist. They get an automatic notification via DM when it goes on discount in the future.
- **Multi-Threaded Architecture:** Handles Telegram updates, deal tracking, wishlist checks, and periodic full game syncs concurrently.
- **Persistent storage:** Uses SQLite to store deals, user wishlists, recent check times, and user/channel relationships.
- **Admin/channel and personal usage:** Notifies both a central channel/group and keeps track of individual private wishlists.

---

## How It Works

1. **Deal Tracking**: The `deals_tracker_worker` thread fetches the latest Steam deals from the CheapShark API every 5 minutes, posting new deals with discounts to your Telegram channel.
2. **Bot Updates**: The `telegram_bot_worker` thread listens for user messages/commands (`/start`, `/search`, `/help`, `/end_notification`) and responds accordingly.
3. **Wishlists**: If a search query isn’t currently on discount, it’s stored in a wishlist. The `check_wishlist_loop` thread periodically checks saved wishlists against current deals and notifies users when their games are discounted.
4. **Full Game Sync**: Optionally syncs an up-to-date discounted game list via [SteamSpy](https://steamspy.com/api.php), keeping local matches fast and relevant.

---

## Installation

> **Requirements:** Python 3.7+, pip

1. **Clone the repository**
    ```bash
    git clone https://github.com/amirhosein1324/Steam-Discount-Channel-Bot.git
    cd Steam-Discount-Channel-Bot
    ```

2. **Install dependencies**
    ```bash
    pip install requests
    ```

3. **Edit your configuration variables in the script**
    - Replace the following at the top of the code:
      - `TELEGRAM_TOKEN` with your bot's API token.
      - `CHANNEL_USERNAME` with your channel's username (starts with `@`).
      - `CHANNEL_LINK` with your channel username (without `@`).

4. **Run the Bot**
    ```bash
    python bot.py
    ```

---

## Configuration

All needed tokens and usernames are set as variables at the top of the script:

```python
TELEGRAM_TOKEN = "YOUR TELEGRAM BOT TOKEN"
CHANNEL_USERNAME = "@YOUR_CHANNEL_USERNAME"
CHANNEL_LINK = "YOUR_CHANNEL_USERNAME_WITHOUT_AT"
```

The database is named `steam.db` by default. You can change the file name if you wish.

---

## Usage (User Commands)

- `/start`  
  Registers the user and sends welcome/help message.

- `/help`  
  Lists available commands and bot features.

- `/search [Game Title]`  
  Searches for a discounted game by title.  
    - If discounted, the bot responds with up to 5 matching current deals.
    - If not currently discounted, the bot notifies the user and adds the game to their wishlist for future monitoring.

- `/end_notification`  
  Clears the user's wishlist and stops future notifications.

---

## Bot Logic Flow

### Main Threads

- **deals_tracker_worker:**  
    - Every 5 minutes: queries CheapShark API for new Steam deals.
    - Posts new deals to your channel, and saves deal info for user lookups.

- **telegram_bot_worker:**  
    - Polls Telegram for messages and commands.
    - Handles user registration, searches, help responses, and wishlist management.

- **check_wishlist_loop:**  
    - Every 60 seconds: checks user wishlists vs. new deals and notifies users if a match is found.

- **get_all_games:**  
    - On startup and every hour: synchronizes a list of all currently discounted games from SteamSpy for improved search/wishlist accuracy.

---

## Database Schema

The bot uses `sqlite3` for all persistent data:

- `deals` – Recent deals (id, title, normalPrice, salePrice, savings, url)
- `times` – Timestamps for when deals were last fetched/updated (id, time)
- `users` – Registered Telegram chat IDs (id, chat_id)
- `wishlist` – User-specific wishlist games to watch for (id, chat_id, game_name)
- `all_games` – Master list of discounted Steam games for rapid searching (id, title, normalPrice, salePrice, savings, url)

---

## Example Output

**Post to Channel Example:**
```
🎮 <b>Half-Life: Alyx</b>
💰 Sale: $29.99
🔥 Discount: 50%
🔗 <a href='https://store.steampowered.com/app/546560'>View Deal</a>
```

**Wishlist Notification Example:**
```
🎯 <b>Wishlist Match Found!</b>
🎮 Portal 2
💰 Sale: $1.99
💵 Normal: $9.99
🔥 Savings: 80%
🔗 <a href='https://store.steampowered.com/app/620'>View on Steam website</a>
```

---
## contact
- [My website](https://www.amirhosseinparsa.ir/)
