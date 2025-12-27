
import re
import os
import asyncio
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes
from PIL import Image

# Import Credentials
from config import OWNER_ID, GEMINI_API_KEY
from database import group_settings_col, active_groups_col, whitelist_col, warnings_col
from ai_engine import get_ai_response, get_translation

# --- DEBUG STARTUP ---
print("--------------------------------------------------")
if not GEMINI_API_KEY:
    print("❌ ERROR: API Key Missing!")
else:
    print(f"✅ API Key Loaded: {GEMINI_API_KEY[:10]}... (Correct)")
print("--------------------------------------------------")

# --- FILTERS ---
# गाली और स्पैम की लिस्ट
BAD_WORDS = ["fuck", "bitch", "scam", "fraud", "porn", "sex", "nude", "xxx", "chutiya", "randi", "bhosdike", "madarchod", "behenchod", "kutta"]
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price", "cheap price", "discount"]

# --- HELPERS ---

async def is_admin(chat_id, user_id, context):
    """Check if user is Admin."""
    if user_id == OWNER_ID: return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def add_warning(user_id, chat_id, context):
    """Add warning and Ban if 3 strikes."""
    try:
        user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
        warnings = user_doc['count'] + 1 if user_doc else 1
        
        warnings_col.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$set': {'count': warnings}},
            upsert=True
        )

        if warnings >= 3:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            return True, "🚫 <b>BANNED!</b> (Limit Reached)"
        
        return False, f"⚠️ <b>Warning {warnings}/3:</b> No Spam/Links!"
    except:
        return False, "⚠️ Warning Added."

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"🎓 <b>Namaste {user.first_name}!</b>\n\n"
        "I am working perfectly now.\n"
        "✅ <b>Security:</b> Active\n"
        "✅ <b>AI Study:</b> Active\n"
    )
    buttons = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message with <code>/tr</code>", parse_mode=ParseMode.HTML)
        return
    
    target = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if target:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        res = await get_translation(target)
        await update.message.reply_text(f"🇮🇳 <b>Translation:</b>\n\n{res}", parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    groups = active_groups_col.count_documents({})
    await update.message.reply_text(f"📊 <b>Active Groups:</b> {groups}", parse_mode=ParseMode.HTML)

async def link_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_chat.id, update.effective_user.id, context):
        await update.message.reply_text("❌ Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/link -100xxxxxxx</code>", parse_mode=ParseMode.HTML)
        return
    try:
        cid = context.args[0]
        chat = await context.bot.get_chat(cid)
        link = chat.invite_link or f"https://t.me/{chat.username}"
        group_settings_col.update_one({'group_id': update.effective_chat.id}, 
                                      {'$set': {'required_channel_id': int(cid), 'channel_link': link, 'channel_name': chat.title}}, upsert=True)
        await update.message.reply_text("✅ <b>Linked!</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def broadcast_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    reply = update.message.reply_to_message
    if not reply: return await update.message.reply_text("Reply to a message.")
    
    msg = await update.message.reply_text("⏳ Sending...")
    groups = active_groups_col.find({})
    count = 0
    for g in groups:
        try:
            if reply.photo: await context.bot.send_photo(g['group_id'], reply.photo[-1].file_id, caption=reply.caption, parse_mode=ParseMode.HTML)
            else: await context.bot.send_message(g['group_id'], reply.text, parse_mode=ParseMode.HTML)
            count += 1
            await asyncio.sleep(0.1)
        except: active_groups_col.delete_one({'group_id': g['group_id']})
    await msg.edit_text(f"✅ Sent to {count} groups.")

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    settings = group_settings_col.find_one({'group_id': req.chat.id})
    if not settings:
        try: await req.approve(); return
        except: return
    try:
        btn = [[InlineKeyboardButton(f"Join {settings['channel_name']}", url=settings['channel_link'])],
               [InlineKeyboardButton("✅ Verify", callback_data=f"chk_{req.chat.id}_{settings['required_channel_id']}")]]
        await context.bot.send_message(req.from_user.id, "Join channel first:", reply_markup=InlineKeyboardMarkup(btn))
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
        except: await q.message.edit_text("⚠️ Error.")

# --- MASTER HANDLER (CORE) ---

async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Update Active Group
    if update.effective_chat.type != 'private':
        active_groups_col.update_one({'group_id': chat_id}, {'$set': {'group_id': chat_id}}, upsert=True)

    text = (msg.text or msg.caption or "").lower()

    # --- 1. SECURITY CHECK ---
    # Check if user is admin
    is_sender_admin = False
    if user:
        is_sender_admin = await is_admin(chat_id, user.id, context)
        
    # If NOT admin, check filters
    if user and not is_sender_admin and update.effective_chat.type != 'private':
        violation = False
        reason = ""

        # Strong Link Regex
        if re.search(r"(https?://|t\.me/|www\.|bit\.ly|\.com)", text):
            violation = True
            reason = "Link"
        elif any(w in text for w in BAD_WORDS):
            violation = True
            reason = "Abuse"
            
        if violation:
            print(f"🚨 VIOLATION: {reason} | User: {user.first_name}")
            try:
                await msg.delete()
                _, warn_msg = await add_warning(user.id, chat_id, context)
                temp = await context.bot.send_message(chat_id, f"{user.mention_html()} {warn_msg}", parse_mode=ParseMode.HTML)
                await asyncio.sleep(5)
                await temp.delete()
                return # STOP processing
            except Exception as e:
                print(f"❌ DELETE FAILED: {e}")
                return

    # --- 2. AI LOGIC ---
    should_reply = False
    
    # Logic: Reply in PM, Reply to Bot, or if specific keywords found
    if update.effective_chat.type == 'private': should_reply = True
    elif msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id: should_reply = True
    elif "?" in text: should_reply = True
    elif any(k in text for k in ["kaise", "what", "solve", "batao", "meaning", "ssc", "exam", "upsc"]): should_reply = True
    elif msg.photo: should_reply = True

    if should_reply:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        
        try:
            response = ""
            if msg.photo:
                f = await msg.photo[-1].get_file()
                path = f"temp_{user.id}.jpg"
                await f.download_to_drive(path)
                img = Image.open(path)
                response = await get_ai_response(msg.caption or "Analyze", image=img)
                if os.path.exists(path): os.remove(path)
            elif text:
                # Ignore short messages in groups
                if update.effective_chat.type != 'private' and len(text) < 4: return
                response = await get_ai_response(text)
            
            if response == "VIOLATION_DETECTED":
                try: await msg.delete()
                except: pass
                await context.bot.send_message(chat_id, "🔞 Content Blocked.")
            elif response:
                try: await msg.reply_text(f"💡 <b>AI Answer:</b>\n\n{response}", parse_mode=ParseMode.MARKDOWN)
                except: await msg.reply_text(f"💡 <b>AI Answer:</b>\n\n{response}")
        except Exception as e:
            print(f"❌ AI Error: {e}")
            await msg.reply_text("⚠️ AI Error. Check Terminal.")
