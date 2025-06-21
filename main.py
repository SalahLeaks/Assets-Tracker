import os
import discord
import aiohttp
import asyncio
import json
import logging
import base64
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  

FORTNITE_PACKS_URL = "https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/fn/offers?lang=en&country=US&count=25"
OAUTH_URL_PACKS = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
EPIC_CLIENT_ID = os.getenv("EPIC_CLIENT_ID")
EPIC_CLIENT_SECRET = os.getenv("EPIC_CLIENT_SECRET")

PACKS_JSON_FILE = "packs.json"

REQUEST_DELAY = 1  
MESSAGE_DELAY = 1  

ENDPOINTS = [
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/mp-item-shop",
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/shopoffervisuals",
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/tournamentinformation",
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/dynamicbackgrounds",
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/crewscreendata"
]

IMAGE_FORMATS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tga", ".bmp")

API_URL = 'https://prm-dialogue-public-api-prod.edea.live.use1a.on.epicgames.com/api/v1/fortnite-br/channel/motd/target'
CLIENT_SECRET = 'M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU='
DEVICE_ID = 'YOUR_DEVICE_ID'
SECRET = 'YOUR_DEVICE_SECRET'
ACCOUNT_ID = 'YOUR_ACCOUNT_ID'

def load_previous_assets():
    try:
        with open("previous_assets.json", "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("No previous assets found or invalid JSON. Starting fresh.")
        return {}

previous_assets = load_previous_assets()

def save_previous_assets():
    with open("previous_assets.json", "w") as file:
        json.dump(previous_assets, file, indent=4)

def load_previous_news_hashes():
    try:
        with open("previous_news_hashes.json", "r") as file:
            data = json.load(file)
            return set(data)  # Convert list to set for faster lookups
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("No previous news hashes found or invalid JSON. Starting fresh for news.")
        return set()

previous_news_hashes = load_previous_news_hashes()

def save_previous_news_hashes():
    with open("previous_news_hashes.json", "w") as file:
        json.dump(list(previous_news_hashes), file, indent=4)

def extract_image_urls(data):
    image_urls = set()  # Use a set to avoid duplicates

    def recursive_search(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and value.split('?')[0].lower().endswith(IMAGE_FORMATS):
                    image_urls.add(value) 
                else:
                    recursive_search(value)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item)

    recursive_search(data)
    logger.debug(f"Extracted image URLs: {image_urls}")
    return image_urls

async def get_refresh_token(session):
    url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
    headers = {"Authorization": f"Basic {CLIENT_SECRET}"}
    data = {
        "grant_type": "device_auth",
        "device_id": DEVICE_ID,
        "secret": SECRET,
        "account_id": ACCOUNT_ID
    }
    async with session.post(url, headers=headers, data=data) as response:
        response.raise_for_status()
        token_data = await response.json()
        logger.debug(f"Refresh token data: {token_data}")
        return token_data.get("refresh_token")

async def get_access_token(session, refresh_token):
    url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
    headers = {
        "Authorization": f"Basic {CLIENT_SECRET}",
        "X-Epic-Device-ID": DEVICE_ID
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "token_type": "eg1"
    }
    async with session.post(url, headers=headers, data=data) as response:
        response.raise_for_status()
        token_data = await response.json()
        logger.debug(f"Access token data: {token_data}")
        return token_data.get("access_token")

async def get_new_packs_token(session):
    auth = base64.b64encode(f"{EPIC_CLIENT_ID}:{EPIC_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials"}
    async with session.post(OAUTH_URL_PACKS, headers=headers, data=data) as response:
        response.raise_for_status()
        token_data = await response.json()
        return token_data.get("access_token")

async def fetch_fortnite_packs(session):
    token = await get_new_packs_token(session)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with session.get(FORTNITE_PACKS_URL, headers=headers) as response:
        response.raise_for_status()
        data = await response.json()

    new_assets = set()
    if "elements" in data:
        for pack in data["elements"]:
            images = pack.get("keyImages", [])
            for image in images:
                url = image.get("url")
                if url and url.startswith(("http://", "https://")):
                    new_assets.add(url)

    try:
        with open(PACKS_JSON_FILE, "r") as f:
            old_assets = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        old_assets = set()

    diff_assets = new_assets - old_assets

    with open(PACKS_JSON_FILE, "w") as f:
        json.dump(list(new_assets), f, indent=4)

    if diff_assets:
        logger.debug(f"New packs assets detected: {diff_assets}")
        return diff_assets
    else:
        logger.debug("No new packs assets detected.")
        return set()

async def fetch_fortnite_news(session):
    refresh_token = await get_refresh_token(session)
    await asyncio.sleep(REQUEST_DELAY)
    access_token = await get_access_token(session, refresh_token)
    await asyncio.sleep(REQUEST_DELAY)

    headers = {"Authorization": f"Bearer {access_token}"}
    json_body = {
        "parameters": {
            "platform": "Windows",
            "language": "en",
            "serverRegion": "EU",
            "country": "DE"
        },
        "tags": ["Product.BR"]
    }
    async with session.post(API_URL, headers=headers, json=json_body) as response:
        response.raise_for_status()
        data = await response.json()
        logger.debug(f"Fortnite news data: {data}")

        new_assets = set()
        if "contentItems" in data:
            current_news_hashes = set()
            for item in data["contentItems"]:
                content_hash = item.get("contentHash")
                if not content_hash:
                    continue
                current_news_hashes.add(content_hash)
                if content_hash not in previous_news_hashes:
                    image_urls = extract_image_urls(item)
                    if image_urls:
                        chosen_url = list(image_urls)[0]
                        new_assets.add(chosen_url)
            # Update the stored news hashes to match the current API response,
            # effectively removing any hashes that no longer exist.
            previous_news_hashes.clear()
            previous_news_hashes.update(current_news_hashes)
        save_previous_news_hashes()
        return new_assets

async def fetch_fortnite_assets(session, retry_count=3):
    detected_changes = set()
    logger.debug("Fetching Fortnite assets...")

    for endpoint in ENDPOINTS:
        attempt = 0
        while attempt < retry_count:
            try:
                async with session.get(endpoint, timeout=10) as response:
                    if response.status == 429:
                        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                        wait_time = (datetime.utcfromtimestamp(reset_time) - datetime.utcnow()).total_seconds()
                        logger.warning(f"Rate limit reached for {endpoint}. Retrying in {wait_time} seconds.")
                        await asyncio.sleep(wait_time + 1)
                        attempt += 1
                        continue
                    data = await response.json()
                    new_assets = extract_image_urls(data)

                    if endpoint in previous_assets:
                        old_assets = set(previous_assets[endpoint].keys())
                        detected_changes.update(new_assets - old_assets)
                    else:
                        detected_changes.update(new_assets)

                    previous_assets[endpoint] = {url: "unknown" for url in new_assets}
                    await asyncio.sleep(REQUEST_DELAY)
                    break

            except aiohttp.ClientError as e:
                logger.error(f"Error fetching assets from {endpoint}: {e}")
                attempt += 1
                if attempt >= retry_count:
                    logger.error(f"Max retries reached for {endpoint}. Skipping.")
                    break
                await asyncio.sleep(2 ** attempt)

    return detected_changes

async def send_asset(url, channel):
    try:
        embed = discord.Embed()
        embed.set_thumbnail(url=url)
        embed.description = url
        await channel.send(embed=embed)
        await asyncio.sleep(MESSAGE_DELAY)
    except discord.HTTPException as e:
        logger.error(f"Error sending asset {url}: {e}")

async def check_for_updates(channel, session):
    logger.debug("Checking for updates...")
    detected_assets = set()

    new_assets = await fetch_fortnite_assets(session)
    detected_assets.update(new_assets)

    try:
        news_assets = await fetch_fortnite_news(session)
        detected_assets.update(news_assets)
    except Exception as e:
        logger.error(f"Error fetching Fortnite news: {e}")

    try:
        packs_assets = await fetch_fortnite_packs(session)
        detected_assets.update(packs_assets)
    except Exception as e:
        logger.error(f"Error fetching Fortnite packs: {e}")

    save_previous_assets()

    if not detected_assets:
        logger.debug("No new assets detected.")
        return

    for asset_url in detected_assets:
        await send_asset(asset_url, channel)

class FortniteBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True  # Ensure the bot can read and send messages
        super().__init__(intents=intents)

    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        channel = self.get_channel(CHANNEL_ID)
        if channel is None:
            logger.error("Channel not found. Please check the CHANNEL_ID.")
            return

        async with aiohttp.ClientSession() as session:
            while True:
                await check_for_updates(channel, session)
                await asyncio.sleep(60)

if __name__ == '__main__':
    try:
        bot = FortniteBot()
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down.")
