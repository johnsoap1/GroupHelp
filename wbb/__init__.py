import asyncio
import logging
import time
from inspect import getfullargspec
from os import path
from pathlib import Path

from aiohttp import ClientSession
from motor.motor_asyncio import AsyncIOMotorClient as MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message
from telegraph import Telegraph

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger("WBB")

# =========================
# Lazy aiohttp session (Py3.12 safe)
# =========================
aiohttpsession = None


async def get_aiohttp_session():
    global aiohttpsession
    if aiohttpsession is None or aiohttpsession.closed:
        aiohttpsession = ClientSession()
    return aiohttpsession


async def close_aiohttp_session():
    global aiohttpsession
    if aiohttpsession and not aiohttpsession.closed:
        await aiohttpsession.close()


# =========================
# Config loader
# =========================
if path.exists("config.py"):
    from config import *
else:
    from sample_config import *

Path("sessions").mkdir(exist_ok=True)

# =========================
# Core constants
# =========================
MOD_LOAD = []
MOD_NOLOAD = []

bot_start_time = time.time()

# =========================
# SUDOERS (FIXED)
# =========================
SUDOERS = set(SUDO_USERS_ID)
SUDOERS_SET = SUDOERS

# =========================
# MongoDB
# =========================
LOGGER.info("Initializing MongoDB client")
mongo_client = MongoClient(MONGO_URL)
db = mongo_client.wbb

# =========================
# Bot client (created in init_bot to avoid event loop issues)
# =========================
app = None

# =========================
# Globals (set after startup)
# =========================
BOT_ID = None
BOT_NAME = None
BOT_USERNAME = None
BOT_MENTION = None
BOT_DC_ID = None
telegraph = None

# =========================
# Sudo loader (kept compatible)
# =========================
async def load_sudoers():
    LOGGER.info("Loading sudoers")
    sudoersdb = db.sudoers

    sudoers = await sudoersdb.find_one({"sudo": "sudo"})
    sudoers = [] if not sudoers else sudoers.get("sudoers", [])

    for user_id in SUDO_USERS_ID:
        SUDOERS.add(user_id)

        if user_id not in sudoers:
            sudoers.append(user_id)
            await sudoersdb.update_one(
                {"sudo": "sudo"},
                {"$set": {"sudoers": sudoers}},
                upsert=True,
            )

    for user_id in sudoers:
        SUDOERS.add(user_id)


# =========================
# Bot initialization (IMPORTANT FIX)
# =========================
async def init_bot():
    global app, BOT_ID, BOT_NAME, BOT_USERNAME, BOT_MENTION, BOT_DC_ID, telegraph

    LOGGER.info("Creating bot client...")
    app = Client(
        "sessions/wbb",
        bot_token=BOT_TOKEN,
        api_id=API_ID,
        api_hash=API_HASH,
    )

    LOGGER.info("Starting bot client...")
    await app.start()

    LOGGER.info("Fetching bot info...")
    me = await app.get_me()

    BOT_ID = me.id
    BOT_NAME = me.first_name + (me.last_name or "")
    BOT_USERNAME = me.username
    BOT_MENTION = me.mention
    BOT_DC_ID = me.dc_id

    LOGGER.info("Initializing Telegraph...")
    telegraph = Telegraph(domain="graph.org")
    telegraph.create_account(short_name=BOT_USERNAME or "WBB")

    LOGGER.info("Bot initialized successfully")


# =========================
# Safe eor helper
# =========================
async def eor(msg: Message, **kwargs):
    func = (
        msg.edit_text
        if msg.from_user and msg.from_user.is_self
        else msg.reply
    )

    spec = getfullargspec(func.__wrapped__).args
    return await func(**{k: v for k, v in kwargs.items() if k in spec})


# =========================
# Export for modules
# =========================
__all__ = [
    "LOGGER",
    "app",
    "db",
    "SUDOERS",
    "SUDOERS_SET",
    "aiohttpsession",
    "get_aiohttp_session",
    "close_aiohttp_session",
    "BOT_ID",
    "BOT_NAME",
    "BOT_USERNAME",
    "BOT_MENTION",
    "BOT_DC_ID",
    "eor",
    "init_bot",
    "load_sudoers",
    "telegraph",
]
