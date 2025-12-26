

# ============================================================



import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, ChatJoinRequestHandler, CallbackQueryHandler, CommandHandler
from telegram.error import BadRequest
import motor.motor_asyncio

# ================= कॉन्फ़िगरेशन (Configuration) =================
BOT_TOKEN = "8265358758:AAE4xUVVEoKcfLVn-BgPhxa9kx43ATww51s"  # अपना बोट टोकन यहाँ डालें
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies" # अपनी MongoDB कनेक्शन स्ट्रिंग डालें
DB_NAME = "TelegramBotDB"
COLLECTION_NAME = "JoinRequests"

# मेन ग्रुप जहाँ लोग जॉइन रिक्वेस्ट भेजेंगे (Group ID)
MAIN_GROUP_ID = -1001940665606

# वो चैनल/ग्रुप्स जिन्हें जॉइन करना अनिवार्य है (ID और Link)
REQUIRED_CHANNELS = [
    {"id": -1002888994822, "link": "https://t.me/noxerXnet"},
    {"id": -1001733704340, "link": "https://t.me/ssc_pdf_books"},
]
# ==============================================================

# लॉगिंग सेट करना
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# MongoDB सेटअप
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("बोट चालू है! मैं जॉइन रिक्वेस्ट हैंडल कर रहा हूँ।")

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    जब कोई यूजर ग्रुप में जॉइन रिक्वेस्ट भेजता है, तो यह फंक्शन चलता है।
    यह यूजर को डेटाबेस में सेव करता है और प्राइवेट मैसेज भेजता है।
    """
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat

    # सिर्फ मेन ग्रुप की रिक्वेस्ट हैंडल करें
    if chat.id != MAIN_GROUP_ID:
        return

    # डेटाबेस में यूजर की जानकारी सेव करें (MongoDB)
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "chat_id": chat.id,
        "status": "pending"
    }
    
    # पुराना डेटा अपडेट करें या नया डालें
    await collection.update_one(
        {"user_id": user.id, "chat_id": chat.id},
        {"$set": user_data},
        upsert=True
    )

    # बटन्स तैयार करना
    keyboard = []
    for channel in REQUIRED_CHANNELS:
        keyboard.append([InlineKeyboardButton("Join Channel", url=channel['link'])])
    
    # Verify बटन (callback_data में user_id और chat_id भेज रहे हैं)
    keyboard.append([InlineKeyboardButton("✅ Verify & Join", callback_data=f"verify_{user.id}_{chat.id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # यूजर को प्राइवेट मैसेज भेजें
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"नमस्ते {user.first_name}! 👋\n\n"
                "मेरी ग्रुप में रिक्वेस्ट एक्सेप्ट करवाने के लिए, "
                "आपको नीचे दिए गए चैनल्स को जॉइन करना होगा।\n\n"
                "सारे चैनल्स जॉइन करने के बाद **Verify** बटन दबाएं।"
            ),
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"मैसेज भेजने में त्रुटि (शायद यूजर ने बोट स्टार्ट नहीं किया): {e}")

async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    जब यूजर 'Verify' बटन दबाता है।
    """
    query = update.callback_query
    await query.answer() # लोडिंग एनीमेशन रोकने के लिए

    data = query.data.split("_")
    user_id = int(data[1])
    group_chat_id = int(data[2])

    not_joined = []

    # चेक करें कि यूजर ने सभी चैनल्स जॉइन किए हैं या नहीं
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            # यूजर member, creator या admin होना चाहिए
            if member.status not in ['member', 'creator', 'administrator']:
                not_joined.append(channel['link'])
        except BadRequest:
            # अगर बोट चैनल में एडमिन नहीं है तो चेक नहीं कर पाएगा
            logging.error(f"बोट चैनल {channel['id']} में एडमिन नहीं है!")
            await query.edit_message_text("Error: मैं चेक नहीं कर पा रहा हूँ। कृपया एडमिन से संपर्क करें।")
            return

    if not_joined:
        # अगर कुछ चैनल जॉइन नहीं किए
        await query.edit_message_text(
            text="❌ आपने अभी तक सारे चैनल्स जॉइन नहीं किए हैं। कृपया जॉइन करें और फिर से कोशिश करें।",
            reply_markup=query.message.reply_markup # बटन वापस दिखाएं
        )
    else:
        # अगर सब जॉइन कर लिया है -> रिक्वेस्ट एक्सेप्ट करें
        try:
            await context.bot.approve_chat_join_request(chat_id=group_chat_id, user_id=user_id)
            
            # डेटाबेस में स्टेटस अपडेट करें
            await collection.update_one(
                {"user_id": user_id, "chat_id": group_chat_id},
                {"$set": {"status": "approved"}}
            )

            await query.edit_message_text(f"✅ बहुत बढ़िया! आपकी रिक्वेस्ट एक्सेप्ट कर ली गई है। आप अब ग्रुप में हैं।")
            
            # (वैकल्पिक) यूजर को ग्रुप लिंक भेज सकते हैं या बस बता दें
            
        except BadRequest as e:
            await query.edit_message_text(f"Error: रिक्वेस्ट एक्सेप्ट नहीं हो पा रही (शायद पहले ही एक्सेप्ट हो चुकी है)।\n{e}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # हैंडलर्स जोड़ना
    application.add_handler(CommandHandler("start", start))
    
    # जब कोई रिक्वेस्ट भेजे
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    
    # जब कोई बटन दबाए
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_"))

    print("Bot is running...")
    application.run_polling()
    
