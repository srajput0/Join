

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    ChatJoinRequestHandler, 
    CallbackQueryHandler, 
    CommandHandler
)
from telegram.error import BadRequest, Forbidden, TelegramError
import motor.motor_asyncio

# ================= सेटिंग्स =================
BOT_TOKEN = "8265358758:AAEh0w0gMyVadZWguiqrYQM6xegfpcy2wiA"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
DB_NAME = "TelegramBotDB"
COLLECTION_NAME = "JoinRequests"

MAIN_GROUP_ID = -1001940665606

REQUIRED_CHANNELS = [
    {"id": -1002888994822, "link": "https://t.me/noxerXnet", "name": "NoxerXnet"},
    {"id": -1001733704340, "link": "https://t.me/ssc_pdf_books", "name": "SSC PDF Books"},
]
# ============================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# MongoDB
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is Online.")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat

    if chat.id != MAIN_GROUP_ID:
        return

    # DB में सेव करें
    await collection.update_one(
        {"user_id": user.id, "chat_id": chat.id},
        {"$set": {"user_id": user.id, "first_name": user.first_name, "status": "pending"}},
        upsert=True
    )

    # बटन बनाएं
    keyboard = []
    for channel in REQUIRED_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"📢 Join {channel['name']}", url=channel['link'])])
    
    keyboard.append([InlineKeyboardButton("✅ Verify & Join", callback_data=f"verify_{user.id}_{chat.id}")])
    
    # यूजर को मैसेज भेजें
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"नमस्ते {user.first_name}!\n\n**{chat.title}** में जुड़ने के लिए नीचे दिए गए चैनल जॉइन करें और फिर **Verify** बटन दबाएं। 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Error sending DM: {e}")

async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    यह फंक्शन चैनल चेक करेगा और अगर बोट एडमिन नहीं है तो एरर बताएगा।
    """
    query = update.callback_query
    await query.answer("Checking...")

    data = query.data.split("_")
    user_id = int(data[1])
    group_chat_id = int(data[2])

    not_joined = []
    admin_error = []

    for channel in REQUIRED_CHANNELS:
        try:
            # यहाँ हम चेक कर रहे हैं
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            
            # अगर मेंबर, एडमिन या क्रिएटर नहीं है
            if member.status not in ['member', 'creator', 'administrator', 'restricted']:
                not_joined.append(channel['name'])
            
            # अगर restricted है (बैन नहीं) तो OK है
            elif member.status == 'restricted' and not member.is_member:
                 not_joined.append(channel['name'])

        except BadRequest as e:
            # 🚨 असली एरर यहाँ पकड़ा जाएगा 🚨
            print(f"❌ Error checking {channel['name']}: {e}")
            admin_error.append(f"❌ Bot is NOT Admin in {channel['name']}")
        except Exception as e:
            print(f"Unknown Error: {e}")
            admin_error.append(f"❌ Error in {channel['name']}")

    # अगर कोई एरर या चैनल बचा है
    if admin_error:
        # अगर बोट एडमिन नहीं है, तो यूजर को सच बता दो
        await query.edit_message_text(
            text=f"⚠️ **System Error:**\n\nमुझे चैनल्स चेक करने की परमिशन नहीं मिल रही है।\n\n{''.join(admin_error)}\n\n(Admin: कृपया बोट को चैनल में एडमिन बनाएं)",
            parse_mode=ParseMode.MARKDOWN
        )
    elif not_joined:
        # अगर यूजर ने चैनल जॉइन नहीं किया
        await query.edit_message_text(
            text="❌ **आपने सारे चैनल जॉइन नहीं किए!**\n\nकृपया जॉइन करें और फिर से Verify दबाएं।",
            reply_markup=query.message.reply_markup
        )
    else:
        # सब सही है -> Approve
        try:
            await context.bot.approve_chat_join_request(chat_id=group_chat_id, user_id=user_id)
            await collection.update_one({"user_id": user_id, "chat_id": group_chat_id}, {"$set": {"status": "approved"}})
            await query.edit_message_text("✅ **Success!** आपकी रिक्वेस्ट एक्सेप्ट कर ली गई है।")
        except BadRequest:
             await query.edit_message_text("⚠️ रिक्वेस्ट पहले ही एक्सेप्ट हो चुकी है।")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_"))

    print("🚀 Bot Started with Error Handling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
