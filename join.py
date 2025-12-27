
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    ChatJoinRequestHandler,
    CallbackQueryHandler,
    CommandHandler
)
from telegram.error import BadRequest, Forbidden
import motor.motor_asyncio

# ================= USER CONFIGURATION =================
BOT_TOKEN = "8265358758:AAE4xUVVEoKcfLVn-BgPhxa9kx43ATww51s"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
DB_NAME = "TelegramBotDB"
COLLECTION_NAME = "JoinRequests"

MAIN_GROUP_ID = -1001940665606

REQUIRED_CHANNELS = [
    {"id": -1002888994822, "link": "https://t.me/noxerXnet"},
    {"id": -1001733704340, "link": "https://t.me/ssc_pdf_books"},
]
# ======================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# MongoDB Connection
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is Running. Waiting for Join Requests.")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    HANDLES THE JOIN REQUEST AND SENDS DM WITHOUT /START
    """
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat

    # Check if request is from the Main Group
    if chat.id != MAIN_GROUP_ID:
        return

    logging.info(f"Join Request Received from: {user.first_name} ({user.id})")

    # 1. Save to Database
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

    # 2. Prepare Buttons
    keyboard = []
    for channel in REQUIRED_CHANNELS:
        keyboard.append([InlineKeyboardButton("📢 Join Channel", url=channel['link'])])
    
    keyboard.append([InlineKeyboardButton("✅ Verify & Join", callback_data=f"verify_{user.id}_{chat.id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 3. SEND DM (The Critical Part)
    # The API allows sending messages to users who triggered a chat_join_request
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"Hello {user.first_name}! 👋\n\n"
                f"To get accepted in **{chat.title}**, you must join our sponsor channels below.\n\n"
                "👇 Join these channels and click **Verify**:"
            ),
            reply_markup=reply_markup
        )
        logging.info(f"Verification message sent to {user.id}")
    except Forbidden:
        logging.error(f"Cannot send message to {user.id}. They might have blocked the bot completely.")
    except Exception as e:
        logging.error(f"Error sending DM: {e}")

async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Verifies if user joined the channels
    """
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
            # Special check for restricted members who are still in the chat
            elif member.status == 'restricted' and not member.is_member:
                 not_joined.append(channel['link'])
        except BadRequest:
            await query.edit_message_text("❌ Error: Bot is not Admin in one of the channels.")
            return

    if not_joined:
        await query.edit_message_text(
            text="❌ You haven't joined all channels yet! Please join and try again.",
            reply_markup=query.message.reply_markup
        )
    else:
        try:
            await context.bot.approve_chat_join_request(chat_id=group_chat_id, user_id=user_id)
            
            await collection.update_one(
                {"user_id": user_id, "chat_id": group_chat_id},
                {"$set": {"status": "approved"}}
            )
            
            await query.edit_message_text(f"✅ Verified! Request Approved.")
        except BadRequest:
             await query.edit_message_text("⚠️ Request already approved or expired.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    
    # This handler captures the event regardless of /start
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_"))

    print("Bot Started...")
    application.run_polling()
