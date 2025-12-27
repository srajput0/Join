# handlers.py
import re
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes
from PIL import Image

from config import OWNER_ID
from database import group_settings_col, active_groups_col, learned_spam_col, whitelist_col, warnings_col
from ai_engine import get_ai_response, get_translation

BAD_WORDS = ["fuck", "bitch", "scam", "fraud", "porn", "sex", "nude", "xxx"]
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price"]

# --- HELPERS ---
async def is_admin(chat_id, user_id, context):
    if user_id == OWNER_ID: return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

async def add_warning(user_id, chat_id, context):
    user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
    warnings = user_doc['count'] + 1 if user_doc else 1
    warnings_col.update_one({'user_id': user_id, 'chat_id': chat_id}, {'$set': {'count': warnings}}, upsert=True)
    
    if warnings >= 3:
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            return True, "🚫 <b>BANNED!</b> You are muted."
        except: return False, "Error banning."
    return False, f"⚠️ <b>Warning {warnings}/3:</b> Behave yourself."

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (f"🎓 <b>Welcome {user.first_name}!</b>\nI am your AI Study & Security Bot.\n\n"
            "🔹 /tr - Translate to Hindi\n🔹 /link - Setup Force Join\n🔹 /stats - Admin Stats")
    buttons = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a msg with <code>/tr</code>", parse_mode=ParseMode.HTML)
        return
    text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if text:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        res = await get_translation(text)
        await update.message.reply_text(f"🇮🇳 <b>Hindi:</b>\n{res}", parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    groups = active_groups_col.count_documents({})
    users = warnings_col.count_documents({})
    await update.message.reply_text(f"📊 <b>Stats:</b>\nActive Groups: {groups}\nWarned Users: {users}", parse_mode=ParseMode.HTML)

async def link_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_chat.id, update.effective_user.id, context): return
    if not context.args:
        await update.message.reply_text("Usage: <code>/link -100xxxxxxx</code> (Channel ID)", parse_mode=ParseMode.HTML)
        return
    try:
        cid = context.args[0]
        chat = await context.bot.get_chat(cid)
        link = chat.invite_link or f"https://t.me/{chat.username}"
        group_settings_col.update_one({'group_id': update.effective_chat.id}, 
                                      {'$set': {'required_channel_id': int(cid), 'channel_link': link, 'channel_name': chat.title}}, upsert=True)
        await update.message.reply_text("✅ <b>Force Join Linked!</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: Make me admin in channel first.\n{e}")

# --- BROADCAST (ADMIN) ---
async def broadcast_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    reply = update.message.reply_to_message
    if not reply: return await update.message.reply_text("Reply to a message to broadcast.")
    
    msg = await update.message.reply_text("⏳ Sending...")
    groups = active_groups_col.find({})
    count = 0
    
    for g in groups:
        try:
            if reply.photo:
                await context.bot.send_photo(g['group_id'], reply.photo[-1].file_id, caption=f"📢 <b>NOTICE</b>\n\n{reply.caption or ''}", parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(g['group_id'], f"📢 <b>NOTICE</b>\n\n{reply.text}", parse_mode=ParseMode.HTML)
            count += 1
            await asyncio.sleep(0.1)
        except:
            active_groups_col.delete_one({'group_id': g['group_id']}) # Remove dead groups
            
    await msg.edit_text(f"✅ Sent to {count} groups.")

# --- JOIN REQUEST ---
async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    settings = group_settings_col.find_one({'group_id': req.chat.id})
    if not settings:
        try: await req.approve() 
        except: pass
        return
    
    try:
        btn = [[InlineKeyboardButton(f"Join {settings['channel_name']}", url=settings['channel_link'])],
               [InlineKeyboardButton("✅ Verify", callback_data=f"chk_{req.chat.id}_{settings['required_channel_id']}")]]
        await context.bot.send_message(req.from_user.id, f"To join <b>{req.chat.title}</b>, join our channel first:", reply_markup=InlineKeyboardMarkup(btn), parse_mode=ParseMode.HTML)
    except: pass

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if "chk_" in q.data:
        _, gid, cid = q.data.split("_")
        try:
            m = await context.bot.get_chat_member(int(cid), q.from_user.id)
            if m.status in ['member', 'administrator', 'creator']:
                await context.bot.approve_chat_join_request(int(gid), q.from_user.id)
                await q.message.edit_text("✅ Approved!")
            else: await q.answer("❌ Not Joined!", show_alert=True)
        except: await q.message.edit_text("⚠️ Error or Expired.")

# --- MASTER HANDLER ---
async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    # SAVE GROUP ID FOR BROADCAST
    if update.effective_chat.type != 'private':
        active_groups_col.update_one({'group_id': update.effective_chat.id}, {'$set': {'group_id': update.effective_chat.id}}, upsert=True)

    user = update.effective_user
    text = (msg.text or msg.caption or "").lower()
    
    # SECURITY
    if not await is_admin(update.effective_chat.id, user.id, context):
        if any(w in text for w in BAD_WORDS) or any(w in text for w in SELLING_KEYWORDS):
            try:
                await msg.delete()
                ban, warn = await add_warning(user.id, update.effective_chat.id, context)
                await context.bot.send_message(update.effective_chat.id, f"{user.mention_html()} {warn}", parse_mode=ParseMode.HTML)
                return
            except: pass

    # AI TRIGGER
    should_reply = (update.effective_chat.type == 'private') or ("?" in text) or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or msg.photo
    
    if should_reply:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        resp = ""
        
        if msg.photo:
            try:
                f = await msg.photo[-1].get_file()
                path = f"temp_{user.id}.jpg"
                await f.download_to_drive(path)
                img = Image.open(path)
                resp = await get_ai_response(msg.caption or "Analyze", image=img)
                if os.path.exists(path): os.remove(path)
            except: pass
        elif len(text) > 2:
            resp = await get_ai_response(text)
            
        if resp == "VIOLATION_DETECTED":
            await msg.delete()
            await context.bot.send_message(update.effective_chat.id, f"🔞 <b>NSFW DETECTED!</b> {user.mention_html()}", parse_mode=ParseMode.HTML)
        elif resp:
            try: await msg.reply_text(f"💡 <b>AI:</b>\n\n{resp}", parse_mode=ParseMode.MARKDOWN)
            except: await msg.reply_text(f"💡 <b>AI:</b>\n\n{resp}")
