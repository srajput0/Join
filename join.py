

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

# ================= आपकी सेटिंग्स (Updated) =================
# आपने जो डिटेल्स दी हैं, वो यहाँ सेट कर दी गई हैं:
BOT_TOKEN = "8207099625:AAGeAXK2s6mloRI8-yjTUf1T1ntt-HHlqWM"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"

DB_NAME = "TelegramBotDB"
COLLECTION_NAME = "JoinRequests"

# आपका मेन ग्रुप ID
MAIN_GROUP_ID = -1001940665606

# आपके चैनल जिन्हें जॉइन करना अनिवार्य है
REQUIRED_CHANNELS = [
    {"id": -1002888994822, "link": "https://t.me/noxerXnet"},
    {"id": -1001733704340, "link": "https://t.me/ssc_pdf_books"},
]
# ==========================================================

# लॉगिंग सेट करना (ताकि एरर दिखे)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# MongoDB कनेक्शन सेटअप
try:
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    logging.info("MongoDB Connected Successfully!")
except Exception as e:
    logging.error(f"MongoDB connection failed: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    सिर्फ यह चेक करने के लिए कि बोट चल रहा है।
    """
    await update.message.reply_text("बोट ऑनलाइन है! Force Join सिस्टम एक्टिव है।")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    यह फंक्शन तब चलता है जब कोई 'Request to Join' बटन दबाता है।
    यह यूजर को प्राइवेट मैसेज भेजेगा (भले ही यूजर ने बोट स्टार्ट न किया हो)।
    """
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat

    # सिर्फ आपके वाले मेन ग्रुप की रिक्वेस्ट को ही प्रोसेस करेंगे
    if chat.id != MAIN_GROUP_ID:
        return

    logging.info(f"New Request: {user.first_name} requested to join {chat.title}")

    # 1. डेटाबेस में यूजर को 'Pending' स्टेटस के साथ सेव करें
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "chat_id": chat.id,
        "status": "pending",
        "request_date": request.date
    }
    
    # डेटाबेस में सेव/अपडेट करें
    await collection.update_one(
        {"user_id": user.id, "chat_id": chat.id},
        {"$set": user_data},
        upsert=True
    )

    # 2. कीबोर्ड (बटन्स) तैयार करना
    keyboard = []
    
    # आपके चैनल्स के लिए बटन
    for channel in REQUIRED_CHANNELS:
        # चैनल का नाम (लिंक से थोड़ा साफ दिखे इसलिए static नाम या लिंक यूज़ कर रहे हैं)
        btn_text = "📢 Join Channel"
        keyboard.append([InlineKeyboardButton(btn_text, url=channel['link'])])
    
    # वेरीफाई बटन
    keyboard.append([InlineKeyboardButton("✅ Verify & Join Group", callback_data=f"verify_{user.id}_{chat.id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 3. यूजर को सीधे प्राइवेट मैसेज भेजें
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"👋 नमस्ते {user.first_name}!\n\n"
                f"आपने **{chat.title}** ग्रुप में जुड़ने की रिक्वेस्ट भेजी है।\n"
                "✅ रिक्वेस्ट अप्रूव करवाने के लिए, नीचे दिए गए चैनल्स को जॉइन करना ज़रूरी है।\n\n"
                "सारे चैनल्स जॉइन करें और फिर **Verify** बटन दबाएं।"
            ),
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Forbidden:
        logging.error(f"User {user.id} has blocked the bot. Message failed.")
    except Exception as e:
        logging.error(f"Error sending DM to {user.id}: {e}")

async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    जब यूजर 'Verify' बटन दबाता है, तो यह चेक करेगा।
    """
    query = update.callback_query
    await query.answer("Checking subscription...") # लोडिंग दिखाएगा

    data = query.data.split("_")
    user_id = int(data[1])
    group_chat_id = int(data[2])

    not_joined_channels = []

    # 4. चेक करें: क्या यूजर ने सारे चैनल जॉइन कर लिए?
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            
            # सिर्फ ये स्टेटस वैलिड माने जाएंगे
            if member.status not in ['member', 'creator', 'administrator', 'restricted']:
                not_joined_channels.append(channel['link'])
            # अगर restricted है (banned नहीं) और member भी है, तो ok है।
            elif member.status == 'restricted' and not member.is_member:
                 not_joined_channels.append(channel['link'])
                 
        except BadRequest as e:
            # अगर बोट चैनल में एडमिन नहीं है, तो एरर आएगा
            logging.error(f"Error checking channel {channel['id']}: {e}")
            await query.edit_message_text(f"❌ Error: मैं चैनल चेक नहीं कर पा रहा हूँ। कृपया एडमिन से संपर्क करें।\n(Bot needs Admin rights in channels)")
            return

    # 5. रिजल्ट
    if not_joined_channels:
        # अगर अभी भी कुछ चैनल जॉइन नहीं किए
        await query.edit_message_text(
            text=(
                "❌ **Access Denied!**\n\n"
                "आपने अभी तक सारे चैनल्स जॉइन नहीं किए हैं।\n"
                "कृपया जॉइन करें और फिर से कोशिश करें।"
            ),
            reply_markup=query.message.reply_markup # पुराने बटन वापस दिखाएं
        )
    else:
        # सब सही है -> रिक्वेस्ट एक्सेप्ट करें
        try:
            await context.bot.approve_chat_join_request(chat_id=group_chat_id, user_id=user_id)
            
            # DB अपडेट
            await collection.update_one(
                {"user_id": user_id, "chat_id": group_chat_id},
                {"$set": {"status": "approved"}}
            )

            await query.edit_message_text(
                f"✅ **Verified!**\n\nआपकी रिक्वेस्ट एक्सेप्ट कर ली गई है। आपका स्वागत है!"
            )
            
        except BadRequest as e:
            await query.edit_message_text("⚠️ आपकी रिक्वेस्ट पहले ही प्रोसेस हो चुकी है।")
            logging.error(f"Approval Error: {e}")

if __name__ == '__main__':
    # एप्लिकेशन बिल्डर
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # हैंडलर्स जोड़ना
    application.add_handler(CommandHandler("start", start))
    
    # सबसे महत्वपूर्ण: जॉइन रिक्वेस्ट हैंडलर
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    
    # बटन हैंडलर
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_"))

    print("🤖 Bot is running with your configuration...")
    application.run_polling()
