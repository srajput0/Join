

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

# --- CONSTANTS ---
BAD_WORDS = ["fuck", "bitch", "scam", "fraud", "porn", "sex", "nude", "xxx", "chutiya", "madarchod", "bhosdike", "randi", "kamina"]
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price", "cheap price", "discount"]

# --- HELPER: ADMIN CHECK (SAFE MODE) ---
async def is_admin(chat_id, user_id, context):
    # Owner is always admin
    if user_id == OWNER_ID: return True
    # If user_id is 0 or None (Anonymous), assume not admin for security, or handle logic
    if not user_id: return False
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        print(f"⚠️ Admin Check Error: {e}")
        return False

# --- HELPER: WARNING SYSTEM ---
async def add_warning(user_id, chat_id, context):
    if not user_id: return False, "" # Can't warn anonymous users
    
    user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
    warnings = user_doc['count'] + 1 if user_doc else 1
    
    warnings_col.update_one(
        {'user_id': user_id, 'chat_id': chat_id},
        {'$set': {'count': warnings}},
        upsert=True
    )

    if warnings >= 3:
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            return True, "🚫 <b>BANNED!</b> You have been muted for 3 violations."
        except Exception as e:
            return False, f"Could not ban: {e}"
    
    return False, f"⚠️ <b>Warning {warnings}/3:</b> No Abuse/Spam/Links allowed!"

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name if user else "User"
    
    text = (
        f"🎓 <b>Namaste {first_name}!</b>\n\n"
        "I am <b>ExamGuard Pro</b>.\n"
        "✅ <b>Security:</b> I delete Bad Words & Links.\n"
        "✅ <b>Study:</b> I solve Math/GK questions.\n"
        "✅ <b>News:</b> I send Exam Updates automatically.\n\n"
        "👇 <b>Admins click below to setup:</b>"
    )
    buttons = [
        [InlineKeyboardButton("⚙️ Admin: Setup Force Join", callback_data="help_forcejoin")],
        [InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message with <code>/tr</code>", parse_mode=ParseMode.HTML)
        return
    
    text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if text:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        res = await get_translation(text)
        await update.message.reply_text(f"🇮🇳 <b>Hindi Translation:</b>\n\n{res}", parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    groups = active_groups_col.count_documents({})
    users = warnings_col.count_documents({})
    await update.message.reply_text(f"📊 <b>Bot Stats:</b>\n\n🏢 Active Groups: {groups}\n⚠️ Warned Users: {users}", parse_mode=ParseMode.HTML)

async def link_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ Only Admins can use this.", parse_mode=ParseMode.HTML)
        return

    if not context.args:
        await update.message.reply_text("Usage: <code>/link -100xxxxxxx</code> (Channel ID)", parse_mode=ParseMode.HTML)
        return

    try:
        cid = context.args[0]
        # Verify Bot is Admin in Channel
        chat = await context.bot.get_chat(cid)
        member = await context.bot.get_chat_member(cid, context.bot.id)
        
        link = chat.invite_link or f"https://t.me/{chat.username}"
        
        group_settings_col.update_one(
            {'group_id': chat_id}, 
            {'$set': {'required_channel_id': int(cid), 'channel_link': link, 'channel_name': chat.title}}, 
            upsert=True
        )
        await update.message.reply_text(f"✅ <b>Linked Successfully!</b>\nMembers must join <b>{chat.title}</b>.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b> Make me ADMIN in the Channel first!\nDetails: {e}", parse_mode=ParseMode.HTML)

async def broadcast_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    reply = update.message.reply_to_message
    if not reply: 
        await update.message.reply_text("Reply to a message to broadcast.")
        return
    
    status_msg = await update.message.reply_text("⏳ Broadcasting...")
    
    groups = active_groups_col.find({})
    count = 0
    failed = 0
    
    for g in groups:
        try:
            if reply.photo:
                await context.bot.send_photo(g['group_id'], reply.photo[-1].file_id, caption=f"📢 <b>NOTICE</b>\n\n{reply.caption or ''}", parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(g['group_id'], f"📢 <b>NOTICE</b>\n\n{reply.text}", parse_mode=ParseMode.HTML)
            count += 1
            await asyncio.sleep(0.1) # Flood control
        except:
            failed += 1
            active_groups_col.delete_one({'group_id': g['group_id']}) # Remove dead groups
            
    await status_msg.edit_text(f"✅ Broadcast Complete!\nSent: {count}\nFailed: {failed}")

# --- JOIN REQUEST & CALLBACKS ---

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    settings = group_settings_col.find_one({'group_id': req.chat.id})
    
    # If no settings, auto approve
    if not settings:
        try: await req.approve() 
        except: pass
        return
    
    try:
        btn = [
            [InlineKeyboardButton(f"🚀 Join {settings['channel_name']}", url=settings['channel_link'])],
            [InlineKeyboardButton("✅ I Have Joined", callback_data=f"chk_{req.chat.id}_{settings['required_channel_id']}")]
        ]
        await context.bot.send_message(
            req.from_user.id, 
            f"👋 To join <b>{req.chat.title}</b>, you must join our channel first.", 
            reply_markup=InlineKeyboardMarkup(btn), 
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Could not DM user: {e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    if q.data == "help_forcejoin":
        await q.message.reply_text("<b>Setup Guide:</b>\n1. Make Bot Admin in Group & Channel.\n2. Use /link CHANNEL_ID in Group.", parse_mode=ParseMode.HTML)
        return

    if "chk_" in q.data:
        _, gid, cid = q.data.split("_")
        try:
            m = await context.bot.get_chat_member(int(cid), q.from_user.id)
            if m.status in ['member', 'administrator', 'creator']:
                await context.bot.approve_chat_join_request(int(gid), q.from_user.id)
                await q.message.edit_text("✅ <b>Approved!</b> You can now chat in the group.", parse_mode=ParseMode.HTML)
            else: 
                await q.answer("❌ You have NOT joined the channel yet!", show_alert=True)
        except: 
            await q.message.edit_text("⚠️ Request Expired or Bot not Admin.")

# --- MASTER MESSAGE HANDLER (THE CORE) ---

async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user = update.effective_user
    
    # 1. Handle Anonymous/Channel Posts (Safely)
    user_id = user.id if user else 0
    user_name = user.first_name if user else "Anonymous"

    # 2. Save Group ID for Broadcast
    if chat_type != 'private':
        active_groups_col.update_one({'group_id': chat_id}, {'$set': {'group_id': chat_id}}, upsert=True)

    # 3. Get Content
    text = (msg.text or msg.caption or "").lower()
    
    # --- SECURITY CHECKS (Admin Bypass) ---
    # We allow Admins to send links/bad words. Everyone else gets checked.
    
    is_sender_admin = False
    if chat_type != 'private' and user_id != 0:
        is_sender_admin = await is_admin(chat_id, user_id, context)

    if not is_sender_admin:
        violation_found = False
        reason = ""

        # A. Check Bad Words
        if any(w in text for w in BAD_WORDS):
            violation_found = True
            reason = "Bad Language"

        # B. Check Selling Keywords
        elif any(w in text for w in SELLING_KEYWORDS):
            violation_found = True
            reason = "Selling/Spam"
            
        # C. Check Links (Regex)
        elif re.search(r"(https?://|t\.me/|www\.)", text):
            # Whitelist check could go here
            violation_found = True
            reason = "Links not allowed"

        if violation_found:
            print(f"🚨 Violation: {reason} by {user_name}")
            try:
                await msg.delete()
                # Only warn if it's a real user
                if user_id != 0:
                    is_banned, warn_msg = await add_warning(user_id, chat_id, context)
                    sent = await context.bot.send_message(chat_id, f"{user.mention_html()} {warn_msg}", parse_mode=ParseMode.HTML)
                    # Auto delete warning after 5 sec to keep chat clean
                    await asyncio.sleep(5)
                    await sent.delete()
                return # STOP HERE
            except Exception as e:
                print(f"❌ Failed to delete message: {e} (Make sure Bot is Admin!)")
    
    # --- AI & REPLY LOGIC ---
    
    should_reply = False
    
    # 1. Private Chat: Always reply
    if chat_type == 'private':
        should_reply = True
        
    # 2. Group Chat: Reply if...
    elif getattr(msg.reply_to_message, 'from_user', None) and msg.reply_to_message.from_user.id == context.bot.id:
        should_reply = True # Reply to bot
    elif "?" in text:
        should_reply = True # Question mark
    elif msg.photo:
        should_reply = True # Photo sent
    elif any(keyword in text for keyword in ["kaise", "what", "solve", "batao", "meaning"]):
        should_reply = True

    if should_reply:
        print(f"🤖 Processing AI Request for {user_name}")
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        
        response_text = ""
        
        # Image Processing
        if msg.photo:
            try:
                photo_file = await msg.photo[-1].get_file()
                path = f"temp_{chat_id}.jpg"
                await photo_file.download_to_drive(path)
                
                img = Image.open(path)
                prompt = msg.caption if msg.caption else "Analyze this image and solve if it's a question."
                
                response_text = await get_ai_response(prompt, image=img)
                if os.path.exists(path): os.remove(path)
            except Exception as e:
                print(f"Image Error: {e}")
                response_text = "⚠️ Error analyzing image."

        # Text Processing
        elif text:
            # Don't reply to very short messages in groups (prevents "Hi" spam)
            if chat_type != 'private' and len(text) < 3: 
                return
            response_text = await get_ai_response(text)

        # Check for Porn/Safety Block
        if response_text == "VIOLATION_DETECTED":
            try:
                await msg.delete()
                await context.bot.send_message(chat_id, f"🔞 <b>NSFW Content Detected!</b> Message deleted.", parse_mode=ParseMode.HTML)
            except: pass
            return

        # Send Reply
        if response_text:
            try:
                # Using Markdown for AI response to support bold/lists
                await msg.reply_text(f"💡 <b>Answer:</b>\n\n{response_text}", parse_mode=ParseMode.MARKDOWN)
            except:
                # Fallback if Markdown fails
                await msg.reply_text(f"💡 <b>Answer:</b>\n\n{response_text}")
