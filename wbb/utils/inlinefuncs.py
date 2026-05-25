"""
MIT License

Copyright (c) 2024 TheHamkerCat

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import asyncio
import os
import sys
from contextlib import suppress
from html import escape
from re import sub as re_sub
from sys import version as pyver
from time import ctime, time

from fuzzysearch import find_near_matches
from motor import version as mongover
from pykeyboard import InlineKeyboard
from pyrogram import __version__ as pyrover
from pyrogram import enums, filters
from pyrogram.raw.functions import Ping
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from search_engine_parser import GoogleSearch

from wbb import (
    BOT_USERNAME,
    MESSAGE_DUMP_CHAT,
    SUDOERS,
    app,
)
from wbb.core.keyboard import ikb
from wbb.core.tasks import _get_tasks_text, all_tasks, rm_task
from wbb.modules.info import get_chat_info, get_user_info
from wbb.modules.music import download_youtube_audio
from wbb.utils.functions import test_speedtest
from wbb.utils.pastebin import paste

keywords_list = [
    "image",
    "wall",
    "tmdb",
    "lyrics",
    "exec",
    "speedtest",
    "search",
    "ping",
    "tr",
    "ud",
    "yt",
    "info",
    "google",
    "torrent",
    "wiki",
    "music",
    "ytmusic",
]


async def inline_help_func(__HELP__):
    buttons = InlineKeyboard(row_width=4)
    buttons.add(
        *[
            (InlineKeyboardButton(text=i, switch_inline_query_current_chat=i))
            for i in keywords_list
        ]
    )
    answerss = [
        InlineQueryResultArticle(
            title="Inline Commands",
            description="Help Related To Inline Usage.",
            input_message_content=InputTextMessageContent(
                "Click A Button To Get Started."
            ),
            thumb_url="https://hamker.me/cy00x5x.png",
            reply_markup=buttons,
        ),
        InlineQueryResultArticle(
            title="Github Repo",
            description="Get Github Respository Of Bot.",
            input_message_content=InputTextMessageContent(
                "https://github.com/thehamkercat/WilliamButcherBot"
            ),
            thumb_url="https://hamker.me/gjc9fo3.png",
        ),
    ]
    answerss = await alive_function(answerss)
    return answerss


async def alive_function(answers):
    buttons = InlineKeyboard(row_width=2)
    bot_state = "Dead" if not await app.get_me() else "Alive"
    buttons.add(
        InlineKeyboardButton("Stats", callback_data="stats_callback"),
        InlineKeyboardButton(
            "Go Inline!", switch_inline_query_current_chat=""
        ),
    )

    msg = f"""
**[William✨](https://github.com/thehamkercat/WilliamButcherBot):**
**MainBot:** `{bot_state}`
**Python:** `{pyver.split()[0]}`
**Pyrogram:** `{pyrover}`
**MongoDB:** `{mongover}`
**Platform:** `{sys.platform}`
**Profile:** [BOT](t.me/{BOT_USERNAME})
"""
    answers.append(
        InlineQueryResultArticle(
            title="Alive",
            description="Check Bot's Stats",
            thumb_url="https://static2.aniimg.com/upload/20170515/414/c/d/7/cd7EEF.jpg",
            input_message_content=InputTextMessageContent(
                msg, disable_web_page_preview=True
            ),
            reply_markup=buttons,
        )
    )
    return answers


async def translate_func(answers, lang, tex):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__TRANSLATION FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Translation disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def urban_func(answers, text):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__URBAN DICTIONARY FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Urban dictionary disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def google_search_func(answers, text):
    gresults = await GoogleSearch().async_search(text)
    limit = 0
    for i in gresults:
        if limit > 48:
            break
        limit += 1

        with suppress(KeyError):
            msg = f"""
[{i['titles']}]({i['links']})
{i['descriptions']}"""

            answers.append(
                InlineQueryResultArticle(
                    title=i["titles"],
                    description=i["descriptions"],
                    input_message_content=InputTextMessageContent(
                        msg, disable_web_page_preview=True
                    ),
                )
            )
    return answers


async def wall_func(answers, text):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__WALLPAPER FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Wallpaper disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def torrent_func(answers, text):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__TORRENT SEARCH FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Torrent search disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def youtube_func(answers, text):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__YOUTUBE SEARCH FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="YouTube search disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def lyrics_func(answers, text):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__LYRICS FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Lyrics disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def tg_search_func(answers, text, user_id):
    # Userbot-only feature disabled in bot-only mode
    msg = "**ERROR**\n__THIS FEATURE IS ONLY AVAILABLE IN USERBOT MODE__"
    answers.append(
        InlineQueryResultArticle(
            title="ERROR",
            description="Userbot-only feature",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def music_inline_func(answers, query):
    # Userbot-only feature disabled in bot-only mode
    msg = "**ERROR**\n__THIS FEATURE IS ONLY AVAILABLE IN USERBOT MODE__"
    answers.append(
        InlineQueryResultArticle(
            title="ERROR",
            description="Userbot-only feature",
            input_message_content=InputTextMessageContent(
                msg, disable_web_page_preview=True
            ),
        )
    )
    return answers


async def wiki_func(answers, text):
    data = await arq.wiki(text)
    if not data.ok:
        answers.append(
            InlineQueryResultArticle(
                title="Error",
                description=data.result,
                input_message_content=InputTextMessageContent(data.result),
            )
        )
        return answers
    data = data.result
    msg = f"""
**QUERY:**
{data.title}

**ANSWER:**
__{data.answer}__"""
    answers.append(
        InlineQueryResultArticle(
            title=data.title,
            description=data.answer,
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def speedtest_init(query):
    answers = []
    user_id = query.from_user.id
    if user_id not in SUDOERS:
        msg = "**ERROR**\n__THIS FEATURE IS ONLY FOR SUDO USERS__"
        answers.append(
            InlineQueryResultArticle(
                title="ERROR",
                description="THIS FEATURE IS ONLY FOR SUDO USERS",
                input_message_content=InputTextMessageContent(msg),
            )
        )
        return answers
    msg = "**Click The Button Below To Perform A Speedtest**"
    button = InlineKeyboard(row_width=1)
    button.add(
        InlineKeyboardButton(text="Test", callback_data="test_speedtest")
    )
    answers.append(
        InlineQueryResultArticle(
            title="Click Here",
            input_message_content=InputTextMessageContent(msg),
            reply_markup=button,
        )
    )
    return answers


# CallbackQuery for the function above


async def test_speedtest_cq(_, cq):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("This Isn't For You!")
    inline_message_id = cq.inline_message_id
    await app.edit_inline_text(inline_message_id, "**Testing**")
    loop = asyncio.get_running_loop()
    download, upload, info = await loop.run_in_executor(None, test_speedtest)
    msg = f"""
**Download:** `{download}`
**Upload:** `{upload}`
**Latency:** `{info['latency']} ms`
**Country:** `{info['country']} [{info['cc']}]`
**Latitude:** `{info['lat']}`
**Longitude:** `{info['lon']}`
"""
    await app.edit_inline_text(inline_message_id, msg)


async def pmpermit_func(answers, user_id, victim):
    # Userbot-only feature disabled in bot-only mode
    return answers


async def ping_func(answers):
    ping = Ping(ping_id=app.rnd_id())
    t1 = time()
    await app.invoke(ping)
    t2 = time()
    ping = f"{str(round((t2 - t1) * 1000, 2))} ms"
    answers.append(
        InlineQueryResultArticle(
            title=ping,
            input_message_content=InputTextMessageContent(f"__**{ping}**__"),
        )
    )
    return answers


async def yt_music_func(answers, url):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__YOUTUBE MUSIC FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="ERROR",
            description="YouTube music disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def info_inline_func(answers, peer):
    not_found = InlineQueryResultArticle(
        title="PEER NOT FOUND",
        input_message_content=InputTextMessageContent("PEER NOT FOUND"),
    )
    try:
        user = await app.get_users(peer)
        caption, _ = await get_user_info(user, True)
    except IndexError:
        try:
            chat = await app.get_chat(peer)
            caption, _ = await get_chat_info(chat, True)
        except Exception:
            return [not_found]
    except Exception:
        return [not_found]

    answers.append(
        InlineQueryResultArticle(
            title="Found Peer.",
            input_message_content=InputTextMessageContent(
                caption, disable_web_page_preview=True
            ),
        )
    )
    return answers


async def tmdb_func(answers, query):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__TMDB FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="TMDB disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def image_func(answers, query):
    # ARQ removed - AI features disabled
    msg = "**ERROR**\n__IMAGE SEARCH FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Image search disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    return answers


async def execute_code(query):
    # ARQ removed - AI features disabled
    text = query.query.strip()
    answers = []
    msg = "**ERROR**\n__CODE EXECUTION FEATURE DISABLED - AI SERVICES REMOVED__"
    answers.append(
        InlineQueryResultArticle(
            title="Error",
            description="Code execution disabled",
            input_message_content=InputTextMessageContent(msg),
        )
    )
    await query.answer(
        results=answers,
        cache_time=1,
    )


async def task_inline_func(user_id):
    if user_id not in SUDOERS:
        return

    tasks = all_tasks()
    text = await _get_tasks_text()
    keyb = None

    if tasks:
        keyb = ikb(
            {i: f"cancel_task_{i}" for i in list(tasks.keys())},
            row_width=4,
        )

    return [
        InlineQueryResultArticle(
            title="Tasks",
            reply_markup=keyb,
            input_message_content=InputTextMessageContent(
                text,
            ),
        )
    ]


async def cancel_task_button(_, query: CallbackQuery):
    user_id = query.from_user.id

    if user_id not in SUDOERS:
        return await query.answer("This is not for you.")

    task_id = int(query.data.split("_")[-1])
    await rm_task(task_id)

    tasks = all_tasks()
    text = await _get_tasks_text()
    keyb = None

    if tasks:
        keyb = ikb({i: f"cancel_task_{i}" for i in list(tasks.keys())})

    await app.edit_inline_text(
        query.inline_message_id,
        text,
    )

    if keyb:
        await app.edit_inline_reply_markup(
            query.inline_message_id,
            keyb,
        )
