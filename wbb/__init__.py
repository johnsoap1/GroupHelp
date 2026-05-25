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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)

# Lazy-initialized aiohttp session for Python 3.12 compatibility
aiohttpsession = None

async def get_aiohttp_session():
    """Get or create aiohttp session (lazy initialization)."""
    global aiohttpsession
    if aiohttpsession is None or aiohttpsession.closed:
        aiohttpsession = ClientSession()
    return aiohttpsession

async def close_aiohttp_session():
    """Close aiohttp session gracefully."""
    global aiohttpsession
    if aiohttpsession and not aiohttpsession.closed:
        await aiohttpsession.close()

is_config = path.exists("config.py")

if is_config:
    from config import *
else:
    from sample_config import *

Path("sessions").mkdir(exist_ok=True)

GBAN_LOG_GROUP_ID = GBAN_LOG_GROUP_ID
WELCOME_DELAY_KICK_SEC = WELCOME_DELAY_KICK_SEC
LOG_GROUP_ID = LOG_GROUP_ID
MESSAGE_DUMP_CHAT = MESSAGE_DUMP_CHAT
MOD_LOAD = []
MOD_NOLOAD = []
SUDOERS = filters.user()
bot_start_time = time.time()


# MongoDB client
LOGGER.info("Initializing MongoDB client")
mongo_client = MongoClient(MONGO_URL)
db = mongo_client.wbb


async def load_sudoers():
    global SUDOERS
    LOGGER.info("Loading sudoers")
    sudoersdb = db.sudoers
    sudoers = await sudoersdb.find_one({"sudo": "sudo"})
    sudoers = [] if not sudoers else sudoers["sudoers"]
    for user_id in SUDO_USERS_ID:
        SUDOERS.add(user_id)
        if user_id not in sudoers:
            sudoers.append(user_id)
            await sudoersdb.update_one(
                {"sudo": "sudo"},
                {"$set": {"sudoers": sudoers}},
                upsert=True,
            )
    if sudoers:
        for user_id in sudoers:
            SUDOERS.add(user_id)


# Userbot client removed - bot only mode
# app2 is no longer initialized

app = Client("sessions/wbb", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

LOGGER.info("Starting bot client")
app.start()

LOGGER.info("Gathering profile info")
x = app.get_me()

BOT_ID = x.id
BOT_NAME = x.first_name + (x.last_name or "")
BOT_USERNAME = x.username
BOT_MENTION = x.mention
BOT_DC_ID = x.dc_id

# Userbot variables removed - bot only mode
USERBOT_ID = BOT_ID
USERBOT_NAME = BOT_NAME
USERBOT_USERNAME = BOT_USERNAME
USERBOT_MENTION = BOT_MENTION
USERBOT_DC_ID = BOT_DC_ID

LOGGER.info("Initializing Telegraph client")
telegraph = Telegraph(domain="graph.org")
telegraph.create_account(short_name=BOT_USERNAME)

# Export LOGGER for use in other modules
__all__ = ["LOGGER"]


async def eor(msg: Message, **kwargs):
    func = (
        (msg.edit_text if msg.from_user.is_self else msg.reply)
        if msg.from_user
        else msg.reply
    )
    spec = getfullargspec(func.__wrapped__).args
    return await func(**{k: v for k, v in kwargs.items() if k in spec})
