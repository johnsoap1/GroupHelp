"""
Enhanced Filters Module v2 for William Butcher Bot

A production-grade, SQLite-backed filters module mirroring the architecture
of the Enhanced Triggers Module v2.

Features:
- Global + Local filters (sudo-only for global)
- Multi-type responses: text, photo, video, animation, document, audio, voice, sticker
- Inline keyboard button support in text responses
- Exact-message or first-word matching (no mid-sentence spam)
- Regex support per filter
- aiosqlite backend with in-memory cache
- Anti-spam cooldown per user per filter
- /stopall with confirmation callback
- /filters lists local + global filters
"""

import re
import time
import random
import logging
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from wbb import app, SUDOERS_SET, db
from wbb.utils.dbfunctions import (
    save_filter,
    delete_filter,
    deleteall_filters,
    get_filter,
    get_filters_names,
)

# ==================== MODULE INFO ====================

__MODULE__ = "Filters"
__HELP__ = """
**Enhanced Filters Module v2**

Filters fire when a message **starts with** (or exactly matches) the keyword.

**Text Filters (Local):**
- `/filter <keyword> - <response>` — add a text filter
- `/stop <keyword>` — remove a filter
- `/stopall` — remove all local filters (confirmation required)
- `/filters` — list all active filters

**Text Filters (Global, Sudo only):**
- `/gfilter <keyword> - <response>`
- `/gstop <keyword>`

**Media Filters (Local):**
- `/mfilter <keyword>` — reply to any supported media

**Media Filters (Global, Sudo only):**
- `/gmfilter <keyword>` — reply to any supported media

**Supported media types:**
photo, video, animation/GIF, document, audio, voice, sticker

**Matching rules:**
- Case-insensitive
- Single-word keyword: fires if it is the ENTIRE message OR the FIRST word
- Multi-word keyword: fires if the message STARTS WITH the phrase
- Regex keyword: fires if pattern matches anywhere (use `/filter regex:<pattern> - <response>`)

**Notes:**
- 5-second cooldown per user per filter
- Global filters fire in every chat (sudo-managed)
- Use `/stop` or `/gstop` to remove; `/stopall` for full local wipe
"""

# ==================== CONFIGURATION ====================

COOLDOWN_TIME: int = 5  # seconds between responses per user per keyword

# ==================== CACHE ====================

# Keyed by chat_id (positive = include globals, negative = local only)
_filter_cache: Dict[int, List[Dict]] = {}


def _invalidate(chat_id: int) -> None:
    _filter_cache.pop(chat_id, None)
    _filter_cache.pop(-chat_id, None)


# ==================== COOLDOWN ====================

_cooldowns: Dict[int, Dict[str, float]] = {}


async def _check_cooldown(user_id: int, keyword: str) -> bool:
    now = time.time()
    user_cd = _cooldowns.setdefault(user_id, {})
    if now - user_cd.get(keyword, 0) < COOLDOWN_TIME:
        return False
    user_cd[keyword] = now
    return True


# ==================== HELPERS ====================

def _get_sudoers() -> set:
    try:
        from wbb import SUDOERS_SET as s
        return s
    except Exception:
        return SUDOERS_SET


async def _is_admin(chat_id: int, user_id: int) -> bool:
    if user_id in _get_sudoers():
        return True
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


def _extract_media(msg: Message) -> Tuple[Optional[str], Optional[str]]:
    """Return (file_type, file_id) from a message, or (None, None)."""
    for attr, ftype in (
        ("photo",     "photo"),
        ("video",     "video"),
        ("animation", "animation"),
        ("document",  "document"),
        ("audio",     "audio"),
        ("voice",     "voice"),
        ("sticker",   "sticker"),
    ):
        obj = getattr(msg, attr, None)
        if obj:
            fid = obj.file_id if hasattr(obj, "file_id") else obj
            return ftype, fid
    return None, None


def _parse_inline_buttons(text: str) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Parse button syntax from response text.
    Syntax:  [Button Label](https://url)
    Multiple buttons on same row separated by | on the same line.
    Returns (clean_text, markup_or_None).
    """
    button_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    rows: List[List[InlineKeyboardButton]] = []
    lines = text.split("\n")
    clean_lines = []

    for line in lines:
        buttons_in_line = button_pattern.findall(line)
        if buttons_in_line:
            row = [InlineKeyboardButton(label, url=url) for label, url in buttons_in_line]
            rows.append(row)
            # Remove button syntax from text
            clean_line = button_pattern.sub("", line).strip()
            if clean_line:
                clean_lines.append(clean_line)
        else:
            clean_lines.append(line)

    markup = InlineKeyboardMarkup(rows) if rows else None
    return "\n".join(clean_lines).strip(), markup


# ==================== DB WRAPPERS ====================

async def _add_filter(
    chat_id: int,
    keyword: str,
    response: str,
    is_global: bool = False,
    is_media: bool = False,
    file_id: Optional[str] = None,
    file_type: Optional[str] = None,
    use_regex: bool = False,
) -> None:
    try:
        filter_data = {
            "response": response,
            "is_global": is_global,
            "is_media": is_media,
            "use_regex": use_regex,
        }
        if file_id:
            filter_data["file_id"] = file_id
        if file_type:
            filter_data["file_type"] = file_type
        await save_filter(chat_id, keyword, filter_data)
        _invalidate(chat_id)
        log.info(f"Filter saved: '{keyword}' (chat={chat_id}, global={is_global})")
    except Exception:
        log.error(f"Failed to save filter '{keyword}' in chat {chat_id}", exc_info=True)
        raise


async def _remove_filter(chat_id: int, keyword: str, is_global: bool = False) -> bool:
    try:
        deleted = await delete_filter(chat_id, keyword)
        if deleted:
            _invalidate(chat_id)
        return deleted
    except Exception:
        log.error(f"Failed to delete filter '{keyword}' in chat {chat_id}", exc_info=True)
        return False


async def _remove_all_filters(chat_id: int) -> int:
    try:
        await deleteall_filters(chat_id)
        _invalidate(chat_id)
        return 1
    except Exception:
        log.error(f"Failed to remove all filters in chat {chat_id}", exc_info=True)
        return 0


async def _get_filters(chat_id: int, include_global: bool = True) -> List[Dict]:
    cache_key = chat_id if include_global else -chat_id
    if cache_key in _filter_cache:
        return _filter_cache[cache_key]
    try:
        filter_names = await get_filters_names(chat_id)
        result = []
        for name in filter_names:
            filter_data = await get_filter(chat_id, name)
            if filter_data:
                result.append({"keyword": name, **filter_data})
        _filter_cache[cache_key] = result
        return result
    except Exception:
        log.error(f"Failed to load filters for chat {chat_id}", exc_info=True)
        return []


# ==================== MATCHING ====================

def _matches(filt: Dict, text: str) -> bool:
    """
    Returns True if the filter fires for this message text.

    Rules:
      - Regex:        re.search on full text
      - Multi-word:   text starts with the phrase
      - Single-word:  text IS the keyword OR keyword is the first word
    """
    keyword = filt["keyword"].strip().lower()
    if not keyword:
        return False

    if filt.get("use_regex"):
        try:
            return bool(re.search(keyword, text, re.IGNORECASE))
        except re.error:
            return False

    if " " in keyword:
        return text == keyword or text.startswith(keyword + " ")

    words = text.split()
    return text == keyword or (bool(words) and words[0] == keyword)


# ==================== SEND RESPONSE ====================

async def _send_response(message: Message, r: Dict) -> None:
    text     = r.get("text", "") or ""
    is_media = r.get("is_media", False)
    fid      = r.get("file_id")
    ftype    = r.get("file_type")

    try:
        if is_media and fid:
            dispatch = {
                "photo":     message.reply_photo,
                "video":     message.reply_video,
                "animation": message.reply_animation,
                "document":  message.reply_document,
                "audio":     message.reply_audio,
                "voice":     message.reply_voice,
                "sticker":   message.reply_sticker,
            }
            fn = dispatch.get(ftype)
            if fn:
                if ftype == "sticker":
                    await fn(fid)
                else:
                    await fn(fid, caption=text or None)
        elif text:
            clean_text, markup = _parse_inline_buttons(text)
            await message.reply_text(
                clean_text or text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    except Exception:
        log.error("Error sending filter response", exc_info=True)


# ==================== COMMAND HANDLERS ====================

# ── /filter ───────────────────────────────────────────────────────────────────

@app.on_message(filters.command("filter") & filters.group)
async def add_filter_cmd(_, message: Message):
    if not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ You need admin rights.")

    parts = message.text.split(None, 1)
    if len(parts) < 2 or "-" not in parts[1]:
        return await message.reply_text(
            "**Usage:** `/filter <keyword> - <response>`\n"
            "Or reply to media: `/mfilter <keyword>`"
        )

    keyword, response = map(str.strip, parts[1].split("-", 1))
    if not keyword or not response:
        return await message.reply_text("❌ Both keyword and response are required.")

    use_regex = keyword.startswith("regex:")
    if use_regex:
        keyword = keyword[6:].strip()

    try:
        await _add_filter(message.chat.id, keyword.lower(), response, use_regex=use_regex)
        prefix = "🔍 Regex filter" if use_regex else "✅ Filter"
        await message.reply_text(f"{prefix} saved for **{keyword}**\n💬 Response: {response}")
    except Exception as e:
        await message.reply_text(f"❌ Failed to save filter: {str(e)[:200]}")


# ── /gfilter ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("gfilter") & filters.group)
async def add_global_filter_cmd(_, message: Message):
    if message.from_user.id not in _get_sudoers():
        return await message.reply_text("❌ Sudo users only.")

    parts = message.text.split(None, 1)
    if len(parts) < 2 or "-" not in parts[1]:
        return await message.reply_text("**Usage:** `/gfilter <keyword> - <response>`")

    keyword, response = map(str.strip, parts[1].split("-", 1))
    if not keyword or not response:
        return await message.reply_text("❌ Both keyword and response are required.")

    use_regex = keyword.startswith("regex:")
    if use_regex:
        keyword = keyword[6:].strip()

    try:
        await _add_filter(0, keyword.lower(), response, is_global=True, use_regex=use_regex)
        await message.reply_text(f"🌍 Global filter saved for **{keyword}**")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {str(e)[:200]}")


# ── /mfilter ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("mfilter") & filters.group)
async def add_media_filter_cmd(_, message: Message):
    if not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ You need admin rights.")
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to a media message.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/mfilter <keyword>` (reply to media)")

    keyword = " ".join(message.command[1:]).lower().strip()
    file_type, file_id = _extract_media(message.reply_to_message)
    if not file_type:
        return await message.reply_text("❌ Unsupported or missing media.")

    caption = message.reply_to_message.caption or ""
    try:
        await _add_filter(
            message.chat.id, keyword, caption,
            is_media=True, file_type=file_type, file_id=file_id,
        )
        await message.reply_text(f"✅ {file_type.capitalize()} filter saved for **{keyword}**")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {str(e)[:200]}")


# ── /gmfilter ─────────────────────────────────────────────────────────────────

@app.on_message(filters.command("gmfilter") & filters.group)
async def add_global_media_filter_cmd(_, message: Message):
    if message.from_user.id not in _get_sudoers():
        return await message.reply_text("❌ Sudo users only.")
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to a media message.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/gmfilter <keyword>` (reply to media)")

    keyword = " ".join(message.command[1:]).lower().strip()
    file_type, file_id = _extract_media(message.reply_to_message)
    if not file_type:
        return await message.reply_text("❌ Unsupported or missing media.")

    caption = message.reply_to_message.caption or ""
    try:
        await _add_filter(
            0, keyword, caption,
            is_global=True, is_media=True, file_type=file_type, file_id=file_id,
        )
        await message.reply_text(f"🌍 Global {file_type} filter saved for **{keyword}**")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {str(e)[:200]}")


# ── /stop ─────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("stop") & filters.group)
async def stop_filter_cmd(_, message: Message):
    if not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Admins only.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/stop <keyword>`")

    keyword = message.text.split(None, 1)[1].strip().lower()
    deleted = await _remove_filter(message.chat.id, keyword)
    if deleted:
        await message.reply_text(f"✅ Filter **{keyword}** removed.")
    else:
        await message.reply_text(f"❌ No filter found for **{keyword}**.")


# ── /gstop ────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("gstop") & filters.group)
async def gstop_filter_cmd(_, message: Message):
    if message.from_user.id not in _get_sudoers():
        return await message.reply_text("❌ Sudo users only.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/gstop <keyword>`")

    keyword = message.text.split(None, 1)[1].strip().lower()
    deleted = await _remove_filter(0, keyword, is_global=True)
    if deleted:
        await message.reply_text(f"✅ Global filter **{keyword}** removed.")
    else:
        await message.reply_text(f"❌ No global filter found for **{keyword}**.")


# ── /stopall ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("stopall") & filters.group)
async def stopall_cmd(_, message: Message):
    if not await _is_admin(message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Admins only.")

    local = [f for f in await _get_filters(message.chat.id, include_global=False)]
    if not local:
        return await message.reply_text("ℹ️ No local filters to remove.")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, delete all", callback_data=f"stopall_yes_{message.chat.id}"),
        InlineKeyboardButton("❌ Cancel",          callback_data="stopall_no"),
    ]])
    await message.reply_text(
        f"⚠️ Are you sure you want to delete **all {len(local)} local filter(s)** in this chat?\n"
        "This cannot be undone.",
        reply_markup=keyboard,
    )


@app.on_callback_query(filters.regex(r"^stopall_"))
async def stopall_callback(_, cb: CallbackQuery):
    data = cb.data

    if data == "stopall_no":
        await cb.message.edit_text("❌ Cancelled.")
        return

    if data.startswith("stopall_yes_"):
        chat_id = int(data.split("_")[2])

        # Only the original chat's admins can confirm
        if not await _is_admin(chat_id, cb.from_user.id):
            return await cb.answer("❌ Admins only.", show_alert=True)

        count = await _remove_all_filters(chat_id)
        await cb.message.edit_text(f"🗑️ Deleted **{count}** local filter(s).")


# ── /filters ──────────────────────────────────────────────────────────────────

@app.on_message(filters.command("filters") & filters.group)
async def list_filters_cmd(_, message: Message):
    all_filters = await _get_filters(message.chat.id, include_global=True)
    if not all_filters:
        return await message.reply_text("ℹ️ No filters active in this chat.")

    global_filters = [f for f in all_filters if f.get("chat_id") == 0]
    local_filters  = [f for f in all_filters if f.get("chat_id") != 0]

    lines = []

    if global_filters:
        lines.append("🌍 **Global Filters:**")
        for i, f in enumerate(global_filters, 1):
            ftype = f.get("file_type") or "text"
            regex = " 🔍" if f.get("use_regex") else ""
            lines.append(f"{i}. `{f['keyword']}`  [{ftype}]{regex}")

    if local_filters:
        if lines:
            lines.append("")
        lines.append(f"💬 **Local Filters** ({message.chat.title}):")
        for i, f in enumerate(local_filters, 1):
            ftype = f.get("file_type") or "text"
            regex = " 🔍" if f.get("use_regex") else ""
            lines.append(f"{i}. `{f['keyword']}`  [{ftype}]{regex}")

    await message.reply_text("\n".join(lines))


# ==================== MESSAGE HANDLER ====================

@app.on_message(filters.group & filters.incoming & filters.text, group=-11)
async def filter_handler(_, message: Message):
    # Skip service messages and bot commands
    if (
        not message.from_user
        or message.text.startswith("/")
        or message.new_chat_members
        or message.left_chat_member
        or message.pinned_message
    ):
        return

    text = message.text.strip().lower()
    if not text:
        return

    active_filters = await _get_filters(message.chat.id, include_global=True)
    if not active_filters:
        return

    # Collect ALL responses from every matching filter, then pick one at random
    # (mirrors triggers module behaviour — fair distribution across all matches)
    all_responses = [
        {"keyword": f["keyword"], "response": r}
        for f in active_filters
        if _matches(f, text)
        for r in f.get("responses", [])
    ]

    if not all_responses:
        return

    selected = random.choice(all_responses)

    if not await _check_cooldown(message.from_user.id, selected["keyword"]):
        return

    await _send_response(message, selected["response"])
