import os

from dotenv import load_dotenv

load_dotenv(
    "config.env" if os.path.isfile("config.env") else "sample_config.env"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SUDO_USERS_ID = list(map(int, os.environ.get("SUDO_USERS_ID", "").split()))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID"))
GBAN_LOG_GROUP_ID = int(os.environ.get("GBAN_LOG_GROUP_ID"))
MESSAGE_DUMP_CHAT = int(os.environ.get("MESSAGE_DUMP_CHAT"))
WELCOME_DELAY_KICK_SEC = int(os.environ.get("WELCOME_DELAY_KICK_SEC", 600))
MONGO_URL = os.environ.get("MONGO_URL")
LOG_MENTIONS = os.environ.get("LOG_MENTIONS", "True").lower() in ["true", "1"]
RSS_DELAY = int(os.environ.get("RSS_DELAY", 300))
PM_PERMIT = os.environ.get("PM_PERMIT", "True").lower() in ["true", "1"]
DEEPL_API = os.environ.get("DEEPL_API")
MUSIC_GROUP_ID = int(os.environ.get("MUSIC_GROUP_ID", "0")) or None
MUSIC_CHANNEL_ID = int(os.environ.get("MUSIC_CHANNEL_ID", "0")) or None
