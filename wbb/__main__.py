import asyncio
import importlib
import re
import sys
from contextlib import suppress

from pyrogram import filters, idle
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from uvloop import install

# Python 3.12 compatibility
if sys.version_info >= (3, 12):
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# Safe uvloop installation
try:
    install()
except Exception:
    pass

from wbb import (
    BOT_NAME,
    BOT_USERNAME,
    LOG_GROUP_ID,
    app,
    LOGGER,
    get_aiohttp_session,
    close_aiohttp_session,
    init_bot,
    load_sudoers,
)
from wbb.utils import paginate_modules
from wbb.utils.dbfunctions import clean_restart_stage

HELPABLE = {}
ALL_MODULES = []


async def start_bot():
    global HELPABLE, ALL_MODULES

    # Initialize bot first (CRITICAL FIX)
    await init_bot()

    # Load sudoers
    await load_sudoers()

    # Assert app is initialized
    assert app is not None, "App must be initialized before loading modules"

    # Import ALL_MODULES after app is initialized
    from wbb.modules import ALL_MODULES

    # Load modules with error handling
    for module in ALL_MODULES:
        try:
            imported_module = importlib.import_module("wbb.modules." + module)
            if (
                hasattr(imported_module, "__MODULE__")
                and imported_module.__MODULE__
            ):
                imported_module.__MODULE__ = imported_module.__MODULE__
                if (
                    hasattr(imported_module, "__HELP__")
                    and imported_module.__HELP__
                ):
                    HELPABLE[
                        imported_module.__MODULE__.replace(" ", "_").lower()
                    ] = imported_module
        except Exception as e:
            LOGGER.error(f"Failed loading module {module}: {e}")
            continue

    bot_modules = ""
    j = 1
    for i in ALL_MODULES:
        if j == 4:
            bot_modules += "|{:<15}|\n".format(i)
            j = 0
        else:
            bot_modules += "|{:<15}".format(i)
        j += 1
    print("+===============================================================+")
    print("|                              WBB                              |")
    print("+===============+===============+===============+===============+")
    print(bot_modules)
    print("+===============+===============+===============+===============+")
    LOGGER.info(f"BOT STARTED AS {BOT_NAME}!")

    restart_data = await clean_restart_stage()

    try:
        LOGGER.info("Sending online status")
        if restart_data:
            await app.edit_message_text(
                restart_data["chat_id"],
                restart_data["message_id"],
                "**Restarted Successfully**",
            )

        else:
            await app.send_message(LOG_GROUP_ID, "Bot started!")
    except Exception:
        pass

    try:
        await idle()
    except KeyboardInterrupt:
        pass

    await close_aiohttp_session()
    LOGGER.info("Stopping clients")
    await app.stop()
    LOGGER.info("Cancelling asyncio tasks")
    for task in asyncio.all_tasks():
        task.cancel()
    LOGGER.info("Dead!")


async def main():
    """Modern async main function for Python 3.12 compatibility."""
    with suppress(asyncio.exceptions.CancelledError):
        await start_bot()
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
