
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    ChatJoinRequestHandler, 
    CallbackQueryHandler, 
    CommandHandler
)
from telegram.error import BadRequest, Forbidden
import motor.motor_asyncio

# ================= CREDENTIALS =================
BOT_TOKEN = "8207099625:AAGeAXK2s6mloRI8-yjTUf1T1ntt-HHlqWM"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
DB_NAME = "TelegramBotDB"
COLLECTION_NAME = "JoinRequests"

MAIN_GROUP_ID = -1001940665606

REQUIRED_CHANNELS = [
    {"id": -1002888994822, "link": "https://t.me/noxerXnet"},
    {"id": -1001733704340, "link": "https://t.me/ssc_pdf_books"},
]
# ===============================================

# लॉगिंग (ताकि स्क्रीन पर दिखे कि क्या हो रहा है)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB
try:
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    print("✅ MongoDB Connected!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is Online & Ready to handle requests.")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    यह फंक्शन जॉइन रिक्वेस्ट आने पर चलता है।
    """
    print("🔔 New Join Request Detected!") # कंसोल में प्रिंट होगा
    
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat

    if chat.id != MAIN_GROUP_ID:
        print(f"⚠️ Request ignored: Wrong Group ID {chat.id}")
        return

    print(f"👤 Processing User: {user.first_name} ({user.id})")

    # DB Entry
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name,
        "chat_id": chat.id,
        "status": "pending",
        "date": request.date
    }
    
    await collection.update_one(
        {"user_id": user.id, "chat_id": chat.id},
        {"$set": user_data},
        upsert=True
    )

    # Buttons
    keyboard = []
    for channel in REQUIRED_CHANNELS:
        keyboard.append([InlineKeyboardButton("📢 Join Channel", url=channel['link'])])
    
    keyboard.append([InlineKeyboardButton("✅ Verify & Join", callback_data=f"verify_{user.id}_{chat.id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Sending Message
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"👋 **नमस्ते {user.first_name}!**\n\n"
                f"आपने **{chat.title}** ग्रुप में रिक्वेस्ट भेजी है।\n"
                "एक्सेप्ट होने के लिए नीचे दिए गए चैनल जॉइन करें और **Verify** बटन दबाएं। 👇"
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        print(f"✅ Message sent to {user.first_name}")
    except Forbidden:
        print(f"❌ Failed: User {user.id} has blocked the bot.")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking...")

    data = query.data.split("_")
    user_id = int(data[1])
    group_chat_id = int(data[2])

    not_joined = []

    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            if member.status not in ['member', 'creator', 'administrator', 'restricted']:
                not_joined.append(channel['link'])
            elif member.status == 'restricted' and not member.is_member:
                 not_joined.append(channel['link'])
        except BadRequest as e:
            await query.edit_message_text(f"❌ Error checking channel: Bot is not admin in {channel['id']}")
            return

    if not_joined:
        await query.edit_message_text(
            text="❌ **आपने सारे चैनल जॉइन नहीं किए!**\nकृपया दोबारा चेक करें।",
            reply_markup=query.message.reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        try:
            await context.bot.approve_chat_join_request(chat_id=group_chat_id, user_id=user_id)
            await collection.update_one(
                {"user_id": user_id, "chat_id": group_chat_id},
                {"$set": {"status": "approved"}}
            )
            await query.edit_message_text("✅ **Verified!** आपकी रिक्वेस्ट एक्सेप्ट कर ली गई है।")
        except BadRequest:
             await query.edit_message_text("⚠️ रिक्वेस्ट पहले ही एक्सेप्ट हो चुकी है।")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_"))

    print("🚀 Bot Started with FORCE UPDATE LISTEN...")
    
    # =================================================================
    # 👇👇👇 असली फिक्स यहाँ है (Allowed Updates) 👇👇👇
    # =================================================================
    application.run_polling(allowed_updates=Update.ALL_TYPES)

