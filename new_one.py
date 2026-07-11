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

USERS_FILE = "users.txt"

REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL and REDIS_URL.startswith("redis://"):
    REDIS_URL = REDIS_URL.replace("redis://", "rediss://", 1)

if REDIS_URL and "ssl_cert_reqs" not in REDIS_URL:
    if "?" in REDIS_URL:
        REDIS_URL += "&ssl_cert_reqs=none"
    else:
        REDIS_URL += "?ssl_cert_reqs=none"

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
FAKE_BASE = 10250

client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

chats_history = {}

def save_user_to_file(user_id, username):
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
    total_users = get_user_count_and_add(user.id, user.username)
    
    if user.id in chats_history:
        del chats_history[user.id]
        
    await update.message.reply_text(
        f"سلام! من Ariadne هستم. هر کاری و هر سوالی داری بپرس تا جواب بدم. 🧩"
    )
    
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=f"🟢 کاربر جدید ربات را استارت کرد:\n👤 نام: {user.full_name}\n🆔 آیدی: {user.id}\n 🏷️ یوزرنیم: {user.username}\n📈 کل کاربران: {total_users:,}"
        )
    except Exception as e:
        logging.error(f"Error sending start log: {e}")

async def handle_multimedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    user_id = user.id
    user_text = message.text or message.caption or ""
    
    save_user_to_file(user_id, user.username)
    try: r.sadd("bot_users", str(user_id))
    except: pass

    forwarded_msg = None
    try:
        forwarded_msg = await context.bot.forward_message(
            chat_id=LOG_GROUP_ID, from_chat_id=update.effective_chat.id, message_id=message.message_id
        )
    except Exception as e: logging.error(f"Forward error: {e}")

    # تشخیص هوشمند درخواست عکس
    trigger_words = ["بکش", "طراحی کن", "نقاشی کن", "عکس بساز", "تصویر بساز", "draw", "paint"]
    is_drawing_request = any(word in user_text.lower() for word in trigger_words)

    if is_drawing_request and not (message.photo or message.video or message.voice or message.audio or message.document):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        try:
            # استفاده از نام مدل استاندارد و بدون پیشوند جهت هماهنگی با API نسخه جدید گوگل
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=user_text,
                config=types.GenerateImagesConfig(
                    number_of_images=1, 
                    output_mime_type="image/jpeg", 
                    aspect_ratio="1:1"
                )
            )
            for generated_image in result.generated_images:
                image_bytes = generated_image.image.image_bytes
                
                # رفع باگ ارسال عکس تلگرام
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=image_bytes,
                    caption=f"🎨 طرح درخواستی شما آماده شد!\n💡 متن: {user_text}",
                    reply_to_message_id=message.message_id
                )
                await context.bot.send_photo(
                    chat_id=LOG_GROUP_ID,
                    photo=image_bytes,
                    caption=f"🎨 طرح هوشمند ساخته شده برای کاربر {user.full_name}:\n{user_text}"
                )
                return
        except Exception as e:
            logging.error(f"Error in Smart Imagen: {e}")
            await update.message.reply_text("❌ متأسفانه درخواست طراحی عکس با خطا مواجه شد یا توسط فیلتر محتوای گوگل رد شد.")
            return

    # روال عادی پیام‌ها و مولتی‌مدیا
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
            file_obj = await message.photo[-1].get_file()
            file_bytes = await file_obj.download_as_bytearray()
            contents.append(types.Part.from_bytes(data=bytes(file_bytes), mime_type="image/jpeg"))
            contents.append(user_text if user_text else "این تصویر را تحلیل کن.")
        elif message.voice or message.audio:
            audio_obj = message.voice if message.voice else message.audio
            file_obj = await audio_obj.get_file()
            file_bytes = await file_obj.download_as_bytearray()
            mime = message.voice.mime_type if message.voice else message.audio.mime_type
            contents.append(types.Part.from_bytes(data=bytes(file_bytes), mime_type=mime))
            contents.append(user_text if user_text else "این فایل صوتی را گوش کن و پاسخ بده.")
        elif message.video:
            file_obj = await message.video.get_file()
            file_bytes = await file_obj.download_as_bytearray()
            contents.append(types.Part.from_bytes(data=bytes(file_bytes), mime_type=message.video.mime_type))
            contents.append(user_text if user_text else "این ویدئو را تحلیل کن.")
        elif message.document and message.document.mime_type == "application/pdf":
            file_obj = await message.document.get_file()
            file_bytes = await file_obj.download_as_bytearray()
            contents.append(types.Part.from_bytes(data=bytes(file_bytes), mime_type="application/pdf"))
            contents.append(user_text if user_text else "این فایل PDF را تحلیل کن.")
        else:
            if not user_text: return
            contents = user_text

        response = chat_session.send_message(contents)
        reply_text = response.text
        
    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        reply_text = "متأسفانه مشکلی در پردازش پیش آمد. دوباره تلاش کنید."

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=reply_text, reply_to_message_id=message.message_id
    )
    
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=f"🤖 پاسخ Ariadne به {user.full_name}:\n\n{reply_text}",
            reply_to_message_id=forwarded_msg.message_id if forwarded_msg else None
        )
    except Exception as e: logging.error(f"Log reply error: {e}")

async def get_users_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.id == LOG_GROUP_ID or user_id == 336303956:
        try:
            all_users = r.smembers("bot_users")
            if all_users:
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    for uid in all_users:
                        f.write(f"{uid}\t@User_From_Database\n")
            if os.path.exists(USERS_FILE):
                await context.bot.send_document(
                    chat_id=update.effective_chat.id, document=open(USERS_FILE, "rb"), caption="📈 لیست کل کاربران"
                )
        except Exception as e: logging.error(f"Backup error: {e}")

def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not REDIS_URL: return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("backup", get_users_backup))
    
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO | filters.Document.ALL) & ~filters.COMMAND, 
        handle_multimedia
    ))

    try: loop = asyncio.get_event_loop()
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
        except Exception as e: logging.error(f"Webhook update error: {e}")
        return web.Response(text="OK")

    async def health_check(request): return web.Response(text="I am alive!")

    app = web.Application()
    app.router.add_post('/telegram', telegram_webhook)
    app.router.add_get('/', health_check)

    loop.run_until_complete(application.start())
    web.run_app(app, host="0.0.0.0", port=PORT, loop=loop)

if __name__ == '__main__':
    main()
