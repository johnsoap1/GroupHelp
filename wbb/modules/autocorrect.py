from pyrogram import filters
from pyrogram.types import Message

from wbb import app


@app.on_message(filters.command("autocorrect"))
async def autocorrect_bot(_, message: Message):
    # ARQ removed - autocorrect feature disabled
    await message.reply_text("❌ Autocorrect feature disabled - ARQ API removed")
