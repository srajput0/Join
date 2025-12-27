
import re
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes
from PIL import Image

from config import OWNER_ID, GEMINI_API_KEY
from database import group_settings_col, active_groups_col, warnings_col
from ai_engine import get_ai_response, get_translation

# --- 1. UPDATED BAD WORDS LIST ---
# आपके स्क्रीनशॉट में 'mc' था, उसे भी जोड़ दिया है
BAD_WORDS = ["fuck", "bitch", "scam", "fraud", "porn", "sex", "nude", "xxx", "chutiya", "randi", "bhosdike", "madarchod", "mc", "bc", "bkl", "kutta", "kamina"]
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price", "cheap price"]

async def is_admin(chat_id, user_id, context):
    if user_id == OWNER_ID: return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

async def add_warning(user_id, chat_id, context):
    try:
        user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
        warnings = user_doc['count'] + 1 if user_doc else 1
        warnings_col.update_one({'user_id': user_id, 'chat_id': chat_id}, {'$set': {'count': warnings}}, upsert=True)
        
        if warnings >= 3:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            return True, "🚫 <b>BANNED!</b>"
        return False, f"⚠️ <b>Warning {warnings}/3</b>"
    except: return False, "⚠️ Warning Added"

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"🎓 <b>Hello {user.first_name}!</b>\nBot is Online & Fixed.\n\n✅ Security Active\n✅ AI Active"
    buttons = [[InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply with <code>/tr</code>", parse_mode=ParseMode.HTML)
        return
    text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if text:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        res = await get_translation(text)
        await update.message.reply_text(f"🇮🇳 <b>Hindi:</b>\n{res}", parse_mode=ParseMode.HTML)

async def link_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_chat.id, update.effective_user.id, context): 
        return await update.message.reply_text("❌ Admins only.")
    if not context.args:
        return await update.message.reply_text("Usage: <code>/link -100xxxxxxx</code>", parse_mode=ParseMode.HTML)
    try:
        cid = context.args[0]
        chat = await context.bot.get_chat(cid)
        link = chat.invite_link or f"https://t.me/{chat.username}"
        group_settings_col.update_one({'group_id': update.effective_chat.id}, 
                                      {'$set': {'required_channel_id': int(cid), 'channel_link': link, 'channel_name': chat.title}}, upsert=True)
        await update.message.reply_text("✅ <b>Linked!</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("❌ Error: Make bot admin in channel.")

# --- MASTER HANDLER ---
async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (msg.text or msg.caption or "").lower()

    # --- 1. SECURITY (Fixed Logic) ---
    # Admins को चेक नहीं करेगा
    is_sender_admin = False
    if user: is_sender_admin = await is_admin(chat_id, user.id, context)

    # अगर एडमिन नहीं है, तो चेक करो
    if user and not is_sender_admin and update.effective_chat.type != 'private':
        violation = False
        
        # 'mc' अब लिस्ट में है, तो डिटेक्ट होगा
        if any(w in text.split() for w in BAD_WORDS): # Exact word match fix
            violation = True
        elif "t.me/" in text or "http" in text:
            violation = True

        if violation:
            try:
                await msg.delete()
                _, warn = await add_warning(user.id, chat_id, context)
                t = await context.bot.send_message(chat_id, f"{user.mention_html()} {warn}", parse_mode=ParseMode.HTML)
                await asyncio.sleep(5)
                await t.delete()
                return # यहाँ से वापस जाओ, AI को कॉल मत करो
            except: pass

    # --- 2. AI LOGIC (Formatting Fixed) ---
    should_reply = False
    if update.effective_chat.type == 'private': should_reply = True
    elif msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id: should_reply = True
    elif "?" in text or "explain" in text or "solve" in text: should_reply = True
    
    if should_reply:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        
        response = ""
        try:
            if text: response = await get_ai_response(text)
        except: response = "⚠️ Error."

        if response:
            # 👇 FIX: HTML Mode use kar rahe hain taaki <b> tag sahi dikhe
            try:
                await msg.reply_text(f"💡 <b>AI Answer:</b>\n\n{response}", parse_mode=ParseMode.HTML)
            except:
                # Agar HTML fail ho jaye (rare), to plain text bhejo
                await msg.reply_text(f"💡 AI Answer:\n\n{response}")
