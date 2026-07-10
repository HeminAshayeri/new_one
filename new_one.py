import os
import logging
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
# استفاده از پکیج جدید و رسمی گوگل
from google import genai
from google.genai import types

import asyncio

# ۱. خواندن توکن‌ها از بخش Environment Variables سرور رندر
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ۲. ساخت کلاینت جمینی با پکیج جدید google-genai
client = genai.Client(api_key=GEMINI_API_KEY)

# فعال‌سازی سیستم لاگ برای دیدن وضعیت در پنل رندر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من بات متصل به جمینی هستم. علاوه بر پیام متنی، می‌تونی برام عکس یا فایل PDF بفرستی و همراهش سوالت رو بپرسی تا برات تحلیلش کنم! 📸📄"
    )

# پردازش جامع پیام‌ها (متن، عکس، فایل)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_text = message.text or message.caption or "این فایل یا تصویر را بررسی و تحلیل کن."
    
    # محتویاتی که قرار است به جمینی فرستاده شود
    contents = [user_text]

    # ارسال وضعیت در حال تایپ به تلگرام
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # الف) بررسی وجود عکس
        if message.photo:
            # گرفتن باکیفیت‌ترین نسخه عکس
            photo_file = await message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            # آماده‌سازی تصویر برای متد جدید جمینی
            image_part = types.Part.from_bytes(
                data=bytes(photo_bytes),
                mime_type="image/jpeg"
            )
            contents.append(image_part)
            
        # ب) بررسی وجود فایل (مثل PDF یا داکیومنت‌ها)
        elif message.document:
            doc = message.document
            # بررسی فرمت فایل
            if doc.mime_type == "application/pdf":
                doc_file = await doc.get_file()
                doc_bytes = await doc_file.download_as_bytearray()
                
                # آماده‌سازی PDF برای متد جدید جمینی
                pdf_part = types.Part.from_bytes(
                    data=bytes(doc_bytes),
                    mime_type="application/pdf"
                )
                contents.append(pdf_part)
            else:
                await message.reply_text("⚠️ در حال حاضر فقط فایل‌های PDF و تصاویر پشتیبانی می‌شوند.")
                return

        # ارسال درخواست به جمینی
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=contents,
        )
        reply_text = response.text
        
    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        reply_text = "متأسفانه در پردازش این درخواست مشکلی پیش اومد. لطفاً دوباره تلاش کنید."

    # فرستادن پاسخ نهایی به کاربر
    await update.message.reply_text(reply_text)

# راه اندازی اصلی بات
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("خطا: توکن تلگرام یا جمینی تعریف نشده است!")
        return

    # ساخت اپلیکیشن تلگرام
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # تعریف هندلرها
    application.add_handler(CommandHandler("start", start))
    
    # فیلتر جدید: ربات علاوه بر متن، به عکس‌ها و داکیومنت‌ها هم گوش می‌دهد
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, 
        handle_message
    ))

    print("بات تلگرام با قابلیت پردازش فایل و عکس روی رندر روشن شد...")
    
    # مدیریت استاندارد لوپ برای پایتون ۳.۱۴ روی رندر
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.updater.start_polling())
    loop.run_until_complete(application.start())
    
    # زنده نگه داشتن برنامه
    loop.run_forever()

if __name__ == '__main__':
    main()
