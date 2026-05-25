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
from wbb.core.keyboard import ikb
from wbb.utils import paginate_modules
from wbb.utils.constants import MARKDOWN
from wbb.utils.dbfunctions import clean_restart_stage, get_rules
from wbb.utils.functions import extract_text_and_keyb

HELPABLE = {}
ALL_MODULES = []


async def start_bot():
    global HELPABLE, ALL_MODULES

    # Initialize bot first (CRITICAL FIX)
    await init_bot()

    # Load sudoers
    await load_sudoers()

    # Register all handlers after app is initialized
    from pyrogram.filters import command

    # Register markdownhelp handler
    from wbb.utils.constants import mkdwnhelp
    app.on_message(command("markdownhelp"))(mkdwnhelp)

    # Register start handler
    app.on_message(filters.command("start"))(start)

    # Register help handler
    app.on_message(filters.command("help"))(help_command)

    # Register callback handlers
    app.on_callback_query(filters.regex("bot_commands"))(commands_callbacc)
    app.on_callback_query(filters.regex("stats_callback"))(stats_callbacc)
    app.on_callback_query(filters.regex(r"help_(.*?)"))(help_button)

    # Register inline module handlers
    from wbb.modules.inline import inline, inline_query_handler
    app.on_message(filters.command("inline"))(inline)
    app.on_inline_query()(inline_query_handler)

    # Register inlinefuncs handlers
    from wbb.utils.inlinefuncs import test_speedtest_cq, cancel_task_button
    app.on_callback_query(filters.regex("test_speedtest"))(test_speedtest_cq)
    app.on_callback_query(filters.regex("^cancel_task_"))(cancel_task_button)

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


home_keyboard_pm = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                text="Commands ❓", callback_data="bot_commands"
            ),
            InlineKeyboardButton(
                text="Repo 🛠",
                url="https://github.com/thehamkercat/WilliamButcherBot",
            ),
        ],
        [
            InlineKeyboardButton(
                text="System Stats 🖥",
                callback_data="stats_callback",
            ),
            InlineKeyboardButton(
                text="Support 👨", url="http://t.me/WBBSupport"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Add Me To Your Group 🎉",
                url=f"http://t.me/{BOT_USERNAME}?startgroup=new",
            )
        ],
    ]
)

home_text_pm = (
    f"Hey there! My name is {BOT_NAME}. I can manage your "
    + "group with lots of useful features, feel free to "
    + "add me to your group."
)

keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                text="Help ❓",
                url=f"t.me/{BOT_USERNAME}?start=help",
            ),
            InlineKeyboardButton(
                text="Repo 🛠",
                url="https://github.com/thehamkercat/WilliamButcherBot",
            ),
        ],
        [
            InlineKeyboardButton(
                text="System Stats 💻",
                callback_data="stats_callback",
            ),
            InlineKeyboardButton(text="Support 👨", url="t.me/WBBSupport"),
        ],
    ]
)


FED_MARKUP = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "Fed Owner Commands", callback_data="fed_owner"
            ),
            InlineKeyboardButton(
                "Fed Admin Commands", callback_data="fed_admin"
            ),
        ],
        [
            InlineKeyboardButton("User Commands", callback_data="fed_user"),
        ],
        [
            InlineKeyboardButton("Back", callback_data="help_back"),
        ],
    ]
)


async def start(_, message):
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply(
            "Pm Me For More Details.", reply_markup=keyboard
        )
    if len(message.text.split()) > 1:
        user = await app.get_users(message.from_user.id)
        name = (message.text.split(None, 1)[1]).lower()
        match = re.match(r"rules_(.*)", name)
        if match:
            chat_id = match.group(1)
            user_id = message.from_user.id
            chat = await app.get_chat(int(chat_id))
            text = f"**The rules for `{chat.title}` are:\n\n**"
            rules = await get_rules(int(chat_id))
            if rules:
                text = text + rules
                if "{chat}" in text:
                    text = text.replace("{chat}", chat.title)
                if "{name}" in text:
                    text = text.replace("{name}", user.mention)
                keyb = None
                if re.findall(r"\[.+\,.+\]", text):
                    text, keyb = extract_text_and_keyb(ikb, text)
                await app.send_message(user_id, text=text, reply_markup=keyb)
            else:
                return await app.send_message(
                    user_id,
                    "The group admins haven't set any rules for this chat yet. "
                    "This probably doesn't mean it's lawless though...!",
                )
        if name == "mkdwn_help":
            await message.reply(
                MARKDOWN,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        elif "_" in name:
            module = name.split("_", 1)[1]
            mod = HELPABLE.get(module)
            if not mod:
                return await message.reply("Module not found.")
            text = (
                f"Here is the help for **{mod.__MODULE__}**:\n"
                + mod.__HELP__
            )
            if module == "federation":
                return await message.reply(
                    text=text,
                    reply_markup=FED_MARKUP,
                    disable_web_page_preview=True,
                )
            await message.reply(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("back", callback_data="help_back")]]
                ),
                disable_web_page_preview=True,
            )
        elif name == "help":
            text, keyb = await help_parser(message.from_user.first_name)
            await message.reply(
                text,
                reply_markup=keyb,
            )
    else:
        await message.reply(
            home_text_pm,
            reply_markup=home_keyboard_pm,
        )
    return


async def help_command(_, message):
    if message.chat.type != ChatType.PRIVATE:
        if len(message.command) >= 2:
            name = (message.text.split(None, 1)[1]).replace(" ", "_").lower()
            if str(name) in HELPABLE:
                key = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="Click here",
                                url=f"t.me/{BOT_USERNAME}?start=help_{name}",
                            )
                        ],
                    ]
                )
                await message.reply(
                    f"Click on the below button to get help about {name}",
                    reply_markup=key,
                )
            else:
                await message.reply(
                    "PM Me For More Details.", reply_markup=keyboard
                )
        else:
            await message.reply(
                "Pm Me For More Details.", reply_markup=keyboard
            )
    else:
        if len(message.command) >= 2:
            name = (message.text.split(None, 1)[1]).replace(" ", "_").lower()
            mod = HELPABLE.get(name)
            if mod:
                text = (
                    f"Here is the help for **{mod.__MODULE__}**:\n"
                    + mod.__HELP__
                )
                await message.reply(text, disable_web_page_preview=True)
            else:
                text, help_keyboard = await help_parser(
                    message.from_user.first_name
                )
                await message.reply(
                    text,
                    reply_markup=help_keyboard,
                    disable_web_page_preview=True,
                )
        else:
            text, help_keyboard = await help_parser(
                message.from_user.first_name
            )
            await message.reply(
                text, reply_markup=help_keyboard, disable_web_page_preview=True
            )
    return


async def help_parser(name, keyboard=None):
    if not keyboard:
        keyboard = InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help"))
    return (
        """Hello {first_name}, My name is {bot_name}.
I'm a group management bot with some useful features.
You can choose an option below, by clicking a button.
Also you can ask anything in Support Group.
""".format(
            first_name=name,
            bot_name=BOT_NAME,
        ),
        keyboard,
    )


async def commands_callbacc(_, CallbackQuery):
    text, keyboard = await help_parser(CallbackQuery.from_user.mention)
    await app.send_message(
        CallbackQuery.message.chat.id,
        text=text,
        reply_markup=keyboard,
    )

    await CallbackQuery.message.delete()


async def stats_callbacc(_, CallbackQuery):
    from wbb.modules.sudoers import bot_sys_stats
    text = await bot_sys_stats()
    await app.answer_callback_query(CallbackQuery.id, text, show_alert=True)


async def help_button(client, query):
    home_match = re.match(r"help_home\((.+?)\)", query.data)
    mod_match = re.match(r"help_module\((.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back", query.data)
    create_match = re.match(r"help_create", query.data)
    top_text = f"""
Hello {query.from_user.first_name}, My name is {BOT_NAME}.
I'm a group management bot with some useful features.
You can choose an option below, by clicking a button.
Also you can ask anything in Support Group.

General command are:
 - /start: Start the bot
 - /help: Give this message
 """
    if mod_match:
        module = (mod_match.group(1)).replace(" ", "_")
        mod = HELPABLE.get(module)
        if not mod:
            return await query.answer("Module not found.")
        text = (
            "{} **{}**:\n".format(
                "Here is the help for", mod.__MODULE__
            )
            + mod.__HELP__
        )
        if module == "federation":
            return await query.message.edit(
                text=text,
                reply_markup=FED_MARKUP,
                disable_web_page_preview=True,
            )
        await query.message.edit(
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("back", callback_data="help_back")]]
            ),
            disable_web_page_preview=True,
        )
    elif home_match:
        await app.send_message(
            query.from_user.id,
            text=home_text_pm,
            reply_markup=home_keyboard_pm,
        )
        await query.message.delete()
    elif prev_match:
        curr_page = int(prev_match.group(1))
        await query.message.edit(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(
                paginate_modules(curr_page - 1, HELPABLE, "help")
            ),
            disable_web_page_preview=True,
        )

    elif next_match:
        next_page = int(next_match.group(1))
        await query.message.edit(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(
                paginate_modules(next_page + 1, HELPABLE, "help")
            ),
            disable_web_page_preview=True,
        )

    elif back_match:
        await query.message.edit(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(
                paginate_modules(0, HELPABLE, "help")
            ),
            disable_web_page_preview=True,
        )

    elif create_match:
        text, keyboard = await help_parser(query)
        await query.message.edit(
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    return await client.answer_callback_query(query.id)


async def main():
    """Modern async main function for Python 3.12 compatibility."""
    with suppress(asyncio.exceptions.CancelledError):
        await start_bot()
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
