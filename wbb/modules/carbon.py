from pyrogram import filters

from wbb import app
from wbb.core.decorators.errors import capture_err
from wbb.utils.functions import make_carbon


@app.on_message(filters.command("carbon"))
@capture_err
async def carbon_func(_, message):
    if not message.reply_to_message:
        return await message.reply_text(
            "Reply to a text message to make carbon."
        )
    if not message.reply_to_message.text:
        return await message.reply_text(
            "Reply to a text message to make carbon."
        )
    status = await message.reply_text("Preparing Carbon…")
    try:
        carbon = await make_carbon(message.reply_to_message.text)
        await status.edit("Uploading…")
        await app.send_document(message.chat.id, carbon)
    except Exception as e:
        await status.edit(f"❌ Failed: {e}")
    else:
        await status.delete()
