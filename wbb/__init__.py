import asyncio
import time
from inspect import getfullargspec
from os import path
from pathlib import Path

from aiohttp import ClientSession
from motor.motor_asyncio import AsyncIOMotorClient as MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message
from telegraph import Telegraph

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


class Log:
    def __init__(self, save_to_file=False, file_name="wbb.log"):
        self.save_to_file = save_to_file
        self.file_name = file_name

    def info(self, msg):
        print(f"[+]: {msg}")
        if self.save_to_file:
            with open(self.file_name, "a") as f:
                f.write(f"[INFO]({time.ctime(time.time())}): {msg}\n")

    def error(self, msg):
        print(f"[-]: {msg}")
        if self.save_to_file:
            with open(self.file_name, "a") as f:
                f.write(f"[ERROR]({time.ctime(time.time())}): {msg}\n")


log = Log(True, "bot.log")

# MongoDB client
log.info("Initializing MongoDB client")
mongo_client = MongoClient(MONGO_URL)
db = mongo_client.wbb


async def load_sudoers():
    global SUDOERS
    log.info("Loading sudoers")
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


loop = asyncio.get_event_loop()
loop.run_until_complete(load_sudoers())

# Userbot client removed - bot only mode
# app2 is no longer initialized

aiohttpsession = ClientSession()

app = Client("sessions/wbb", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

log.info("Starting bot client")
app.start()

log.info("Gathering profile info")
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

log.info("Initializing Telegraph client")
telegraph = Telegraph(domain="graph.org")
telegraph.create_account(short_name=BOT_USERNAME)


async def eor(msg: Message, **kwargs):
    func = (
        (msg.edit_text if msg.from_user.is_self else msg.reply)
        if msg.from_user
        else msg.reply
    )
    spec = getfullargspec(func.__wrapped__).args
    return await func(**{k: v for k, v in kwargs.items() if k in spec})
