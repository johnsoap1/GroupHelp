from wbb import app
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import asyncio
import time
from deep_translator import GoogleTranslator

# Initialize optional imports
DEEPL_API = None
translate_col = None

try:
    from wbb import DEEPL_API as DEEPL_KEY
    DEEPL_API = DEEPL_KEY
    if DEEPL_API:
        import deepl
except Exception as e:
    print(f"[WARNING] DeepL not available: {e}")

try:
    from wbb.core.mongo import db
    translate_col = db.translate_history
except Exception as e:
    print(f"[WARNING] MongoDB not available: {e}")

__MODULE__ = "Translate"
__HELP__ = """
**🌐 Translate Module**

Translate text between languages using DeepL (if configured) or Google Translate as fallback.

**Commands:**
- /translate [lang] — Translate replied text to the specified language
- /langs — Show all supported language codes
- /tlhelp — Show help

Example:
Reply /translate es → translates to Spanish
Reply /translate spanish → translates to Spanish
"""

# Supported languages
GOOGLE_LANGS = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian", "zh-cn": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi",
    "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "vi": "Vietnamese",
    "th": "Thai", "sv": "Swedish", "cs": "Czech", "ro": "Romanian"
}

LANG_ALIASES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "chinese": "zh-cn",
    "japanese": "ja", "korean": "ko", "arabic": "ar", "hindi": "hi",
    "dutch": "nl", "polish": "pl", "turkish": "tr", "vietnamese": "vi",
    "thai": "th", "swedish": "sv", "czech": "cs", "romanian": "ro"
}

# DeepL language codes (different from Google)
DEEPL_LANGS = {
    "en": "EN-US", "es": "ES", "fr": "FR", "de": "DE",
    "it": "IT", "pt": "PT-PT", "ru": "RU", "zh": "ZH",
    "ja": "JA", "nl": "NL", "pl": "PL", "cs": "CS",
    "sv": "SV", "ro": "RO", "tr": "TR"
}

def normalize_language(lang_input: str) -> str:
    """Normalize language input to standard code."""
    lang = lang_input.lower().strip()
    return LANG_ALIASES.get(lang, lang)

def chunk_text(text: str, size: int = 4500):
    """Split text into chunks for translation."""
    return [text[i:i + size] for i in range(0, len(text), size)]

def translate_text(text: str, target_lang: str, source_lang: str = "auto"):
    """Translate text using DeepL (if available) or Google."""
    target = normalize_language(target_lang)
    
    if not target:
        return None, None, "Invalid language code"

    # Try DeepL if API key available
    if DEEPL_API and target in DEEPL_LANGS:
        try:
            import deepl
            translator = deepl.Translator(DEEPL_API)
            chunks = chunk_text(text, 4500)
            result_parts = []
            
            for chunk in chunks:
                result = translator.translate_text(
                    chunk,
                    target_lang=DEEPL_LANGS[target],
                    source_lang=None  # Auto-detect
                )
                result_parts.append(result.text)
            
            detected = None
            return " ".join(result_parts), "DeepL", detected
        except Exception as e:
            print(f"[WARN] DeepL failed: {e}")
            # Fall through to Google

    # Fallback to Google Translate
    try:
        # Handle special case for Chinese
        google_target = "zh-CN" if target == "zh-cn" or target == "zh" else target
        
        # Check if language is supported
        if google_target not in GOOGLE_LANGS and target not in GOOGLE_LANGS:
            return None, None, f"Language '{target}' not supported"
        
        translator = GoogleTranslator(source="auto", target=google_target)
        chunks = chunk_text(text, 4500)
        translated_parts = []
        
        for chunk in chunks:
            result = translator.translate(chunk)
            translated_parts.append(result)
        
        return " ".join(translated_parts), "Google", None
    except Exception as e:
        print(f"[ERROR] Google Translate failed: {e}")
        return None, None, str(e)

async def save_translation(user_id, source_text, translated, src_lang, tgt_lang, service):
    """Save translation to database."""
    if translate_col is None:
        return
    try:
        await translate_col.insert_one({
            "user_id": user_id,
            "source_text": source_text[:500],
            "translated_text": translated[:500],
            "source_lang": src_lang,
            "target_lang": tgt_lang,
            "service": service,
            "timestamp": time.time(),
        })
    except Exception as e:
        print(f"[ERROR] Failed to save history: {e}")

@app.on_message(filters.command("translate"))
async def translate_command(client, message: Message):
    """Handle /translate command."""
    if not message.reply_to_message:
        return await message.reply_text(
            "❌ Please reply to a message with /translate <language>\n"
            "Example: /translate es or /translate spanish"
        )

    text = message.reply_to_message.text or message.reply_to_message.caption
    if not text:
        return await message.reply_text("❌ No text found in the replied message.")

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ Usage: /translate <language>\n"
            "Examples:\n"
            "• /translate es (Spanish)\n"
            "• /translate french (French)\n"
            "• /translate de (German)\n\n"
            "Use /langs to see all supported languages."
        )

    target_lang = message.command[1]
    msg = await message.reply_text("🔄 Translating...")

    try:
        # Run translation in executor to avoid blocking
        loop = asyncio.get_running_loop()
        translated, service, error = await loop.run_in_executor(
            None, translate_text, text, target_lang, "auto"
        )

        if not translated:
            error_msg = error or "Translation failed. Try again later."
            return await msg.edit_text(f"❌ {error_msg}")

        # Save to history
        await save_translation(
            message.from_user.id,
            text,
            translated,
            "auto",
            target_lang,
            service
        )

        # Trim long output
        if len(translated) > 4000:
            translated = translated[:4000] + "\n\n... [truncated]"

        # Format language name
        lang_name = GOOGLE_LANGS.get(normalize_language(target_lang), target_lang.upper())

        # Create response with copy button
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Copy", callback_data="copy_translation")]]
        )

        await msg.edit_text(
            f"🌐 **Translation** ({service})\n"
            f"**To:** {lang_name}\n\n"
            f"{translated}",
            reply_markup=markup,
        )

        # Delete command message after successful translation
        try:
            await message.delete()
        except Exception:
            pass

    except Exception as e:
        print(f"[ERROR] Translation error: {e}")
        import traceback
        traceback.print_exc()
        await msg.edit_text(f"❌ Error: {str(e)[:200]}")

@app.on_message(filters.command("langs"))
async def langs_command(_, message: Message):
    """Show all supported languages."""
    # Format languages nicely
    lang_list = []
    for code, name in sorted(GOOGLE_LANGS.items(), key=lambda x: x[1]):
        lang_list.append(f"• `{code}` — {name}")
    
    langs_text = "\n".join(lang_list)
    
    response = (
        "**🌍 Supported Languages**\n\n"
        f"{langs_text}\n\n"
        "**Usage:** /translate <code> or /translate <name>\n"
        "Example: /translate es or /translate spanish"
    )
    
    await message.reply_text(response)

@app.on_message(filters.command("tlhelp"))
async def tl_help(_, message: Message):
    """Show translate help."""
    await message.reply_text(__HELP__)

print("✅ translate.py loaded")
