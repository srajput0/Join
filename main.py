


import logging
import re
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ChatMemberHandler
from pymongo import MongoClient
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from PIL import Image

# ================= CONFIGURATION =================
# Replace these with your actual details
BOT_TOKEN = "8265358758:AAEh0w0gMyVadZWguiqrYQM6xegfpcy2wiA"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
OWNER_ID = 8177972152  # Your numeric Telegram ID
GEMINI_API_KEY = "AIzaSyBfzkP06CzIMVITdEz3V6EWBcsPNvkvrHI"

# ================= AI CONFIGURATION (Gemini) =================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 1. System Prompt (The Bot's Personality - English)
SYSTEM_PROMPT = """
You are 'ExamGuard', an expert Study Companion and Exam Guide (UPSC, SSC, Railway, Banking).
1. Language: Answer strictly in clear, professional English.
2. Math/Science: Solve problems step-by-step.
3. Guidance: Provide authentic, verified study roadmaps.
4. Tone: Helpful, motivating, and strict against nonsense.
5. If the input is just a greeting, reply politely. If it's a question, answer it.
"""

# 2. Safety Settings (Strict Porn/NSFW Blocker)
# This configuration forces AI to BLOCK nude/sexual content immediately.
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

# ================= DATABASE CONNECTION =================
try:
    client = MongoClient(MONGO_URI)
    db = client['UltimateStudyBot']
    
    # Collections
    force_join_col = db['force_join']       # For Force Join Channels
    learned_spam_col = db['learned_spam']   # Self-learning spam database
    whitelist_col = db['whitelist']         # Allowed words
    warnings_col = db['user_warnings']      # User warning count
    
    print("✅ System Online: Database & AI Connected Successfully!")
except Exception as e:
    print(f"❌ Database Error: {e}")

# ================= LOGGING =================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= SECURITY FILTERS =================
# Static bad words list
BAD_WORDS = ["fuck", "bitch", "bastard", "idiot", "scam", "fraud", "sex", "porn", "nude", "xxx", "asshole"]
# Selling keywords
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price", "cheap price", "sale", "purchase"]

# ================= HELPER FUNCTIONS =================

async def is_admin(chat_id, user_id, context):
    """Check if user is Admin or Owner"""
    if user_id == OWNER_ID: return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def add_warning(user_id, chat_id, context):
    """Adds a warning. Returns (is_banned, message)"""
    user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
    warnings = user_doc['count'] + 1 if user_doc else 1
    
    warnings_col.update_one(
        {'user_id': user_id, 'chat_id': chat_id},
        {'$set': {'count': warnings}},
        upsert=True
    )

    if warnings >= 3:
        # Mute the user
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            return True, "🚫 **BANNED!** You have been muted for repeated violations."
        except Exception as e:
            return False, f"Error banning: {e}"
    
    return False, f"⚠️ **Warning {warnings}/3:** Please follow the rules or you will be banned."

async def get_ai_response(text_prompt, image=None):
    """Sends content to Gemini AI with Safety Checks"""
    try:
        if image:
            response = model.generate_content(
                [SYSTEM_PROMPT, text_prompt, image], 
                safety_settings=SAFETY_SETTINGS
            )
        else:
            chat = model.start_chat(history=[])
            response = chat.send_message(
                SYSTEM_PROMPT + "\nUser Input: " + text_prompt,
                safety_settings=SAFETY_SETTINGS
            )
        
        # Check if AI blocked it due to Safety Ratings (NSFW)
        if response.prompt_feedback.block_reason:
            return "VIOLATION_DETECTED"
        
        # Sometimes response text is empty if filtered internally
        if not response.text:
             return "VIOLATION_DETECTED"

        return response.text

    except Exception as e:
        # If the error is related to Safety/Blocking
        if "finish_reason" in str(e) or "safety" in str(e).lower():
             return "VIOLATION_DETECTED"
        logger.error(f"AI Error: {e}")
        return "" 

# ================= COMMAND HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"🎓 **Welcome, {user.first_name}!**\n\n"
        "I am your **AI Study Companion & Group Guard**.\n"
        "🔹 **Ask Me:** Send any study question or photo (Math/Science).\n"
        "🔹 **Updates:** Get official exam notifications.\n"
        "🔹 **Protection:** I auto-delete Spam, Abuse, and NSFW content.\n\n"
        "👇 **Select an Option:**"
    )
    buttons = [
        [InlineKeyboardButton("📰 Official Exam Links", callback_data="news_hub")],
        [InlineKeyboardButton("👮 SSC Roadmap", callback_data="map_ssc"), InlineKeyboardButton("🏛 UPSC Roadmap", callback_data="map_upsc")],
        [InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

# --- Broadcast (Admin Only) ---
async def broadcast_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID: return

    # Usage: /broadcast <Message>
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("⚠️ Usage: `/broadcast Exam Results Out!`")
        return

    chat_id = update.effective_chat.id
    sent_msg = await context.bot.send_message(
        chat_id, 
        f"🚨 **OFFICIAL STUDY UPDATE** 🚨\n\n{msg}\n\n🔔 *Check Official Websites immediately.*",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        await context.bot.pin_chat_message(chat_id, sent_msg.message_id)
    except:
        pass

# --- Self Learning Commands (Admin Only) ---
async def learn_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if not await is_admin(chat_id, user.id, context): return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a spam message with `/spam` to teach me.")
        return

    spam_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if spam_text:
        learned_spam_col.insert_one({'keyword': spam_text.lower()})
        await update.message.reply_to_message.delete()
        await update.message.delete()
        await context.bot.send_message(chat_id, "🧠 **Learned!** Added to spam database.")

async def whitelist_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Usage: /allow hello
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not await is_admin(chat_id, user.id, context): return
    
    if not context.args: return
    word = " ".join(context.args).lower()
    
    whitelist_col.update_one({'word': word}, {'$set': {'word': word}}, upsert=True)
    learned_spam_col.delete_many({'keyword': word})
    await update.message.reply_text(f"✅ **Approved!** '{word}' is now allowed.")

# --- Callback Buttons ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "news_hub":
        txt = (
            "🔗 **Official Authentic Websites:**\n\n"
            "🔹 **SSC:** ssc.nic.in\n"
            "🔹 **UPSC:** upsc.gov.in\n"
            "🔹 **Railways:** indianrailways.gov.in\n"
            "🔹 **IBPS:** ibps.in\n"
        )
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "map_ssc":
        await query.message.reply_text("📘 **SSC Roadmap:**\n1. Master Arithmetic (Rakesh Yadav).\n2. Reasoning (PYQs).\n3. English (Neetu Singh Vol 1).")
    elif data == "map_upsc":
        await query.message.reply_text("🏛 **UPSC Roadmap:**\n1. NCERTs (6-12th).\n2. Read 'The Hindu' daily.\n3. Polity (Laxmikant).")

# ================= MASTER HANDLER (Security + AI) =================

async def master_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (msg.text or msg.caption or "").lower()
    is_pm = update.effective_chat.type == 'private'

    # --- 1. SECURITY & SPAM CHECK (Skip for Admins) ---
    if not await is_admin(chat_id, user.id, context):
        
        # A. Whitelist Check
        whitelisted = [doc['word'] for doc in whitelist_col.find({})]
        if any(w in text for w in whitelisted):
            pass # Skip checks if word is whitelisted
        else:
            violation_found = False
            reason = ""

            # Check Learned Spam
            learned_spams = [doc['keyword'] for doc in learned_spam_col.find({})]
            
            if any(spam in text for spam in learned_spams):
                violation_found = True; reason = "Spam Detected (AI)"
            elif re.search(r"(https?://|t\.me/)", text):
                violation_found = True; reason = "Links not allowed"
            elif any(w in text for w in BAD_WORDS):
                violation_found = True; reason = "Abusive Language"
            elif any(w in text for w in SELLING_KEYWORDS):
                violation_found = True; reason = "Selling is Prohibited"

            if violation_found:
                try:
                    await msg.delete()
                    is_banned, warn_msg = await add_warning(user.id, chat_id, context)
                    await context.bot.send_message(chat_id, f"{user.mention_html()} {warn_msg}", parse_mode=ParseMode.HTML)
                    return # Stop processing
                except Exception as e:
                    logger.error(f"Error in Security: {e}")

    # --- 2. INTELLIGENT AI TRIGGER ---
    
    should_reply = False
    
    # Trigger Logic:
    # 1. Always reply in PM.
    # 2. In Group: Reply if replying to bot, OR contains Question Mark, OR contains trigger words, OR has an Image.
    trigger_words = ["how", "what", "why", "solve", "explain", "meaning", "define", "roadmap", "guide", "kaise", "kya"]
    
    if is_pm:
        should_reply = True
    elif msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
        should_reply = True
    elif "?" in text:
        should_reply = True
    elif any(word in text for word in trigger_words):
        should_reply = True
    elif msg.photo: 
        # Always scan photos for safety, but reply only if it looks like a query
        should_reply = True 

    # --- 3. EXECUTE AI PROCESSING ---
    if should_reply:
        # Show typing status
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        response_text = ""
        
        # A. HANDLE IMAGE (Vision + Porn Check)
        if msg.photo:
            try:
                photo_file = await msg.photo[-1].get_file()
                file_path = f"temp_{user.id}.jpg"
                await photo_file.download_to_drive(file_path)
                
                img = Image.open(file_path)
                prompt = msg.caption if msg.caption else "Analyze this image accurately. If it's a problem, solve it."
                
                # Call AI
                response_text = await get_ai_response(prompt, image=img)
                
                # Cleanup
                if os.path.exists(file_path): os.remove(file_path)
            except Exception as e:
                logger.error(f"Image Error: {e}")
        
        # B. HANDLE TEXT
        elif text:
            # Ignore very short messages in groups to prevent spam
            if len(text) < 4 and not is_pm: return 
            response_text = await get_ai_response(text)

        # --- 4. CHECK FOR VIOLATION (PORNOGRAPHY) ---
        if response_text == "VIOLATION_DETECTED":
            try:
                await msg.delete()
                is_banned, warn_msg = await add_warning(user.id, chat_id, context)
                await context.bot.send_message(
                    chat_id, 
                    f"🔞 {user.mention_html()} **SENT NSFW/PORN CONTENT!**\nDetected by AI Shield. Message Deleted.\n{warn_msg}",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Error deleting porn: {e}")
            return # Do not send any reply

        # --- 5. SEND NORMAL AI REPLY ---
        if response_text:
            await msg.reply_text(f"💡 **AI Answer:**\n\n{response_text}", parse_mode=ParseMode.MARKDOWN)

# ================= MAIN EXECUTION =================

def main():
    print("🚀 Ultimate Bot Started...")
    print("🛡️ Security: Active")
    print("🔞 Anti-Porn: Active (AI Powered)")
    print("🧠 Self-Learning: Active")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_alert)) # Admin Notification
    app.add_handler(CommandHandler("spam", learn_spam)) # Train Bot
    app.add_handler(CommandHandler("allow", whitelist_word)) # Fix False Positives

    # Callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # Master Handler (Handles Text, Photos, Security, AI)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.LEFT_CHAT_MEMBER, master_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
