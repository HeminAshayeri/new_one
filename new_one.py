import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
# استفاده از پکیج جدید و رسمی گوگل
from google import genai

# ۱. خواندن توکن‌ها از بخش Environment Variables سرور رندر (برای امنیت بالا)
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
        "سلام! من بات متصل به هوش مصنوعی جمینی (Gemini) هستم که روی سرور رندر میزبانی می‌شم. هر سوالی داری ازم بپرس!"
    )


# پاسخ به پیام‌های متنی کاربران
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # ارسال وضعیت در حال تایپ به تلگرام
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # متد جدید پکیج برای تولید پاسخ از جمینی
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_text,
        )
        reply_text = response.text
    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        reply_text = "متأسفانه در ارتباط با هوش مصنوعی مشکلی پیش اومد. لطفاً دوباره تلاش کنید."

    # فرستادن پاسخ نهایی به کاربر
    await update.message.reply_text(reply_text)


# راه اندازی اصلی بات
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("خطا: توکن تلگرام یا جمینی در تنظیمات سرور (Env Vars) تعریف نشده است!")
        return

    # ساخت اپلیکیشن تلگرام (بدون نیاز به پروکسی روی سرور رندر)
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # تعریف هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("بات تلگرام با موفقیت روی سرور رندر روشن شد و در حال گوش دادن به پیام‌هاست...")
    application.run_polling()


if __name__ == '__main__':
    main()