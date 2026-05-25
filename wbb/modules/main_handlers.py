import re
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatType

from wbb import BOT_NAME, BOT_USERNAME, app, LOGGER
from wbb.utils import paginate_modules
from wbb.utils.constants import MARKDOWN
from wbb.utils.dbfunctions import get_rules
from wbb.utils.functions import extract_text_and_keyb
from wbb.core.keyboard import ikb

__MODULE__ = "Main Handlers"
__HELP__ = """
**Main Commands:**

/start - Start the bot
/help - Get help menu
"""

HELPABLE = {}


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
                parse_mode="HTML",
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
    else:
        text, help_keyboard = await help_parser(message.from_user.mention)
        await message.reply(
            text,
            reply_markup=help_keyboard,
            disable_web_page_preview=True,
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


@app.on_message(filters.command("start"))
async def start_handler(_, message):
    await start(_, message)


@app.on_message(filters.command("help"))
async def help_handler(_, message):
    await help_command(_, message)


@app.on_callback_query(filters.regex("bot_commands"))
async def commands_callbacc(_, CallbackQuery):
    text, keyboard = await help_parser(CallbackQuery.from_user.mention)
    await app.send_message(
        CallbackQuery.message.chat.id,
        text=text,
        reply_markup=keyboard,
    )

    await CallbackQuery.message.delete()


@app.on_callback_query(filters.regex("stats_callback"))
async def stats_callbacc(_, CallbackQuery):
    from wbb.modules.sudoers import bot_sys_stats
    text = await bot_sys_stats()
    await app.answer_callback_query(CallbackQuery.id, text, show_alert=True)


@app.on_callback_query(filters.regex(r"help_(.*?)"))
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
    if home_match:
        text, keyboard = await help_parser(query.from_user.mention)
        await query.message.edit(
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    elif mod_match:
        module = mod_match.group(1)
        text = (
            "{} **{}**:\n".format(
                "Here is the help for", HELPABLE[module].__MODULE__
            )
            + HELPABLE[module].__HELP__
        )
        await query.message.edit(
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("back", callback_data="help_back")]]
            ),
            disable_web_page_preview=True,
        )
    elif prev_match:
        module = prev_match.group(1)
        current = HELPABLE.keys()
        index = list(current).index(module)
        if index == 0:
            index = len(current) - 1
        else:
            index -= 1
        new_mod = list(current)[index]
        text = (
            "{} **{}**:\n".format(
                "Here is the help for", HELPABLE[new_mod].__MODULE__
            )
            + HELPABLE[new_mod].__HELP__
        )
        await query.message.edit(
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [
                    paginate_modules(
                        index,
                        HELPABLE,
                        "help",
                    )
                ]
            ),
            disable_web_page_preview=True,
        )
    elif next_match:
        module = next_match.group(1)
        current = HELPABLE.keys()
        index = list(current).index(module)
        if index == len(current) - 1:
            index = 0
        else:
            index += 1
        new_mod = list(current)[index]
        text = (
            "{} **{}**:\n".format(
                "Here is the help for", HELPABLE[new_mod].__MODULE__
            )
            + HELPABLE[new_mod].__HELP__
        )
        await query.message.edit(
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [
                    paginate_modules(
                        index,
                        HELPABLE,
                        "help",
                    )
                ]
            ),
            disable_web_page_preview=True,
        )
    elif back_match:
        text, keyboard = await help_parser(query.from_user.mention)
        await query.message.edit(
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    elif create_match:
        await query.answer("This feature is not available!", show_alert=True)

    return await client.answer_callback_query(query.id)


keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Commands", callback_data="bot_commands"),
        ],
        [
            InlineKeyboardButton("Stats", callback_data="stats_callback"),
        ],
    ]
)

home_keyboard_pm = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Commands", callback_data="bot_commands"),
        ],
        [
            InlineKeyboardButton("Stats", callback_data="stats_callback"),
        ],
    ]
)

home_text_pm = f"""Hello there, I am {BOT_NAME}.
I can help you manage your groups.

Click on the buttons below to see what I can do.
"""

FED_MARKUP = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("User Commands", callback_data="fed_user"),
        ],
        [
            InlineKeyboardButton("Back", callback_data="help_back"),
        ],
    ]
)
