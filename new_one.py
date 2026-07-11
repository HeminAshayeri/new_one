import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from aiohttp import web
import asyncio

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# رندر خودش این متغیر را به ما می‌دهد، اگر نبود روی ۱۰۰۰۰ تنظیم می‌شود
PORT = int(os.environ.get("PORT", 10000))
# آدرس یو‌آر‌ال ربات شما در رندر
RENDER_URL = "https://gemini-bot-w3zw.onrender.com"

client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

chats_history = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chats_history:
        del chats_history[user_id]
    await update.message.reply_text(
        "سلام! من آریادنه (Ariadne) هستم؛ معمار هوش مصنوعی شما. 🧩\n\n"
        "هر کاری و هر سوالی داری بپرس تا جواب بدم."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    user_text = message.text or message.caption or ""
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if user_id not in chats_history:
        chats_history[user_id] = client.chats.create(model='gemini-3.1-flash-lite')
    
    chat_session = chats_history[user_id]
    contents = []

    try:
        if message.photo:
            photo_file = await message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            image_part = types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg")
            contents.append(image_part)
            contents.append(user_text if user_text else "این تصویر را تحلیل کن.")
        elif message.document and message.document.mime_type == "application/pdf":
            doc_file = await message.document.get_file()
            doc_bytes = await doc_file.download_as_bytearray()
            pdf_part = types.Part.from_bytes(data=bytes(doc_bytes), mime_type="application/pdf")
            contents.append(pdf_part)
            contents.append(user_text if user_text else "این فایل PDF را تحلیل کن.")
        else:
            if not user_text:
                return
            contents = user_text

        response = chat_session.send_message(contents)
        reply_text = response.text
        
    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        reply_text = "متأسفانه مشکلی در پردازش پیش آمد. دوباره تلاش کنید."

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=reply_text,
        reply_to_message_id=message.message_id
    )

def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("خطا: توکن‌ها تعریف نشده‌اند!")
        return

    # ۱. ساخت اپلیکیشن تلگرام
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, 
        handle_message
    ))

    # ۲. تنظیم دسترسی لوپ پایتون
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # مقداردهی اولیه ربات
    loop.run_until_complete(application.initialize())
    
    # ست کردن وب‌هوک در سرور تلگرام
    webhook_url = f"{RENDER_URL}/telegram"
    loop.run_until_complete(application.bot.set_webhook(url=webhook_url))
    logging.info(f"Webhook set to: {webhook_url}")

    # ۳. ساخت سرور وب واقعی با aiohttp برای پاسخ به تلگرام و رندر
    async def telegram_webhook(request):
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        except Exception as e:
            logging.error(f"Error processing update: {e}")
        return web.Response(text="OK")

    async def health_check(request):
        return web.Response(text="I am alive!")

    app = web.Application()
    app.router.add_post('/telegram', telegram_webhook)
    app.router.add_get('/', health_check) # این همان صفحه‌ایست که رندر چک می‌کند

    # شروع ربات
    loop.run_until_complete(application.start())
    
    # اجرای سرور روی پورت ۱۰۰۰۰
    web.run_app(app, host="0.0.0.0", port=PORT, loop=loop)

if __name__ == '__main__':
    main()
