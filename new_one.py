import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from aiohttp import web
import asyncio
import redis

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))
RENDER_URL = "https://gemini-bot-w3zw.onrender.com"
LOG_GROUP_ID = -1004318756097  # شناسه گروه تلگرامی شما

# فایل ذخیره‌سازی لیست کاربران روی سرور
USERS_FILE = "users.txt"

# اصلاح پروتکل و آدرس اتصال به دیتابیس امن Upstash
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL and REDIS_URL.startswith("redis://"):
    REDIS_URL = REDIS_URL.replace("redis://", "rediss://", 1)

# اصلاح پارامتر اتصال منطبق با نسخه 8 کتابخانه Redis پایتون
r = redis.Redis.from_url(
    REDIS_URL, 
    decode_responses=True, 
    ssl_verify_cert=False,  # فرمت کاملاً صحیح پارامتر در نسخه جدید ریدیس
    ssl_connection_class=redis.SSLConnection
)

FAKE_BASE = 10250
client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

chats_history = {}

def save_user_to_file(user_id, username):
    """ذخیره اطلاعات کاربر در دو ستون مجزا روی فایل موقت"""
    try:
        username_str = f"@{username}" if username else "No_Username"
        user_line = f"{user_id}\t{username_str}\n"
        
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                if str(user_id) in f.read():
                    return
                    
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(user_line)
    except Exception as e:
        logging.error(f"Error saving user to file: {e}")

def get_user_count_and_add(user_id, username):
    save_user_to_file(user_id, username)
    try:
        r.ping()
        r.sadd("bot_users", str(user_id))
        actual_count = r.scard("bot_users")
        return FAKE_BASE + actual_count
    except Exception as e:
        logging.error(f"🔴 Connection Failed - Redis error: {e}")
        return FAKE_BASE

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    if user_id in chats_history:
        del chats_history[user_id]
        
    total_users = get_user_count_and_add(user_id, username)
    
    await update.message.reply_text(
        f"سلام! من Ariadne هستم. هر کاری و هر سوالی داری بپرس تا جواب بدم. 🧩"
    )
    
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=f"🟢 کاربر جدید ربات را استارت کرد:\n"
                 f"👤 نام: {user.full_name}\n"
                 f"🆔 آیدی عددی: {user_id}\n"
                 f"🏷️ یوزرنیم: @{username if username else 'ندارد'}\n"
                 f"📈 کل کاربران فعلی: {total_users:,}"
        )
    except Exception as e:
        logging.error(f"Error sending start log to group: {e}")

async def get_users_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازسازی فایل بک‌آپ مستقیم از روی دیتابیس ابدی Upstash هنگام درخواست ادمین"""
    user_id = update.effective_user.id
    if update.effective_chat.id == LOG_GROUP_ID or user_id == 336303956:
        try:
            # بیرون کشیدن تمام آیدی‌ها از دیتابیس ابدی Upstash
            all_users = r.smembers("bot_users")
            if all_users:
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    for uid in all_users:
                        f.write(f"{uid}\t@User_From_Database\n")
            
            if os.path.exists(USERS_FILE):
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(USERS_FILE, "rb"),
                    caption="📈 لیست کل کاربران ربات (استخراج مستقیم از دیتابیس ابدی Upstash)"
                )
            else:
                await update.message.reply_text("هنوز هیچ کاربری در دیتابیس ذخیره نشده است.")
        except Exception as e:
            logging.error(f"Backup generation failed: {e}")
            await update.message.reply_text("خطا در ارتباط با دیتابیس جهت ساخت بک‌آپ.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    user_id = user.id
    user_text = message.text or message.caption or ""
    
    save_user_to_file(user_id, user.username)
    try:
        r.sadd("bot_users", str(user_id))
    except:
        pass

    forwarded_msg = None
    try:
        forwarded_msg = await context.bot.forward_message(
            chat_id=LOG_GROUP_ID,
            from_chat_id=update.effective_chat.id,
            message_id=message.message_id
        )
    except Exception as e:
        logging.error(f"Error forwarding user message to group: {e}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    bot_persona = (
        "تنظیمات هویتی ادمین: نام تو Ariadne (آریادنه) است. "
        "اگر کاربر از تو پرسید اسمت چیه، تو کی هستی، نامت چیست یا هر سوالی مربوط به هویتت کرد، "
        "باید صراحتاً و با لحنی دوستانه بگویی: 'من اسمم Ariadne هستم' یا 'من Ariadne هستم'."
    )

    if user_id not in chats_history:
        chats_history[user_id] = client.chats.create(
            model='gemini-3.1-flash-lite',
            config=types.GenerateContentConfig(system_instruction=bot_persona)
        )
    
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
    
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=f"🤖 پاسخ Ariadne به {user.full_name}:\n\n{reply_text}",
            reply_to_message_id=forwarded_msg.message_id if forwarded_msg else None
        )
    except Exception as e:
        logging.error(f"Error sending bot reply to group: {e}")

def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not REDIS_URL:
        print("خطا: متغیرهای محیطی تعریف نشده‌اند!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("backup", get_users_backup))
    
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, 
        handle_message
    ))

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(application.initialize())
    
    webhook_url = f"{RENDER_URL}/telegram"
    loop.run_until_complete(application.bot.set_webhook(url=webhook_url))

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
    app.router.add_get('/', health_check)

    loop.run_until_complete(application.start())
    web.run_app(app, host="0.0.0.0", port=PORT, loop=loop)

if __name__ == '__main__':
    main()
