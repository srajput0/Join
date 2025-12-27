
import re
import os
import asyncio
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes
from PIL import Image

# Import Configuration and Database
from config import OWNER_ID, GEMINI_API_KEY
from database import group_settings_col, active_groups_col, whitelist_col, warnings_col
from ai_engine import get_ai_response, get_translation

# --- DEBUG: CHECK API KEY ---
if not GEMINI_API_KEY:
    print("❌ CRITICAL ERROR: API Key is MISSING in config.py")
else:
    print(f"✅ API Key Loaded: {GEMINI_API_KEY[:10]}... (Ready)")

# --- SECURITY FILTERS ---
BAD_WORDS = ["fuck", "bitch", "scam", "fraud", "porn", "sex", "nude", "xxx", "chutiya", "randi", "bhosdike", "madarchod", "behenchod", "kutta", "kamina"]
SELLING_KEYWORDS = ["buy batch", "paid course", "dm for price", "cheap price", "lelo", "discount"]

# --- HELPER FUNCTIONS ---

async def is_admin(chat_id, user_id, context):
    """Checks if a user is Admin/Owner."""
    if user_id == OWNER_ID: return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def add_warning(user_id, chat_id, context):
    """Adds a warning to the user. Bans if warnings >= 3."""
    try:
        user_doc = warnings_col.find_one({'user_id': user_id, 'chat_id': chat_id})
        warnings = user_doc['count'] + 1 if user_doc else 1
        
        warnings_col.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$set': {'count': warnings}},
            upsert=True
        )

        if warnings >= 3:
            # BAN USER
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            return True, "🚫 <b>BANNED!</b> (3/3 Warnings Limit Reached)"
        
        return False, f"⚠️ <b>Warning {warnings}/3:</b> Please follow the group rules!"
    except Exception as e:
        print(f"Warning System Error: {e}")
        return False, "⚠️ Warning added."

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name if user else "User"
    
    text = (
        f"🎓 <b>Namaste {first_name}!</b>\n\n"
        "I am <b>ExamGuard Pro</b> - Your AI Study & Security Bot.\n\n"
        "🛡️ <b>Security:</b> I auto-delete Links & Abuse.\n"
        "🤖 <b>AI Study:</b> Ask me any question.\n"
        "🇮🇳 <b>Translate:</b> Reply with <code>/tr</code> to translate.\n"
        "📢 <b>Updates:</b> I send Exam News automatically.\n\n"
        "👇 <b>Options:</b>"
    )
    buttons = [
        [InlineKeyboardButton("⚙️ Setup Force Join (Admins)", callback_data="help_forcejoin")],
        [InlineKeyboardButton("➕ Add Me to Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Translates replied message to Hindi."""
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ <b>Usage:</b> Reply to a message with <code>/tr</code>", parse_mode=ParseMode.HTML)
        return
    
    target_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if target_text:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        translated_text = await get_translation(target_text)
        await update.message.reply_text(f"🇮🇳 <b>Hindi Translation:</b>\n\n{translated_text}", parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only stats."""
    if update.effective_user.id != OWNER_ID: return
    
    groups = active_groups_col.count_documents({})
    warned_users = warnings_col.count_documents({})
    
    await update.message.reply_text(
        f"📊 <b>Bot Statistics:</b>\n\n"
        f"🏢 <b>Active Groups:</b> {groups}\n"
        f"⚠️ <b>Warned Users:</b> {warned_users}",
        parse_mode=ParseMode.HTML
    )

async def link_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Connects a Channel for Force Join."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ Only Group Admins can use this.", parse_mode=ParseMode.HTML)
        return

    if not context.args:
        await update.message.reply_text("<b>Usage:</b>\n<code>/link -100xxxxxxx</code> (Your Channel ID)", parse_mode=ParseMode.HTML)
        return

    try:
        channel_id = context.args[0]
        # Check if Bot is Admin in Channel
        chat = await context.bot.get_chat(channel_id)
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        
        invite_link = chat.invite_link or f"https://t.me/{chat.username}"
        
        # Save to DB
        group_settings_col.update_one(
            {'group_id': chat_id}, 
            {'$set': {'required_channel_id': int(channel_id), 'channel_link': invite_link, 'channel_name': chat.title}}, 
            upsert=True
        )
        await update.message.reply_text(f"✅ <b>Success!</b> Members must now join <b>{chat.title}</b>.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b> Make me ADMIN in that Channel first!\n\nDetails: {e}", parse_mode=ParseMode.HTML)

async def broadcast_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends message to all groups."""
    if update.effective_user.id != OWNER_ID: return
    
    reply = update.message.reply_to_message
    if not reply: 
        await update.message.reply_text("Reply to a message (Text/Photo) to broadcast.")
        return
    
    msg = await update.message.reply_text("⏳ Broadcasting started...")
    
    groups = active_groups_col.find({})
    count = 0
    
    for g in groups:
        try:
            if reply.photo:
                await context.bot.send_photo(g['group_id'], reply.photo[-1].file_id, caption=reply.caption, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(g['group_id'], reply.text, parse_mode=ParseMode.HTML)
            count += 1
            await asyncio.sleep(0.1) 
        except:
            active_groups_col.delete_one({'group_id': g['group_id']}) # Remove inactive groups
            
    await msg.edit_text(f"✅ <b>Broadcast Complete!</b>\nSent to: {count} groups.", parse_mode=ParseMode.HTML)

# --- JOIN REQUEST HANDLER (FORCE JOIN) ---

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    settings = group_settings_col.find_one({'group_id': req.chat.id})
    
    # If no settings, auto-approve
    if not settings:
        try: await req.approve()
        except: pass
        return
    
    try:
        # Send DM to user
        buttons = [
            [InlineKeyboardButton(f"🚀 Join {settings['channel_name']}", url=settings['channel_link'])],
            [InlineKeyboardButton("✅ I Have Joined", callback_data=f"chk_{req.chat.id}_{settings['required_channel_id']}")]
        ]
        await context.bot.send_message(
            req.from_user.id,
            f"👋 <b>Hello!</b>\nTo join <b>{req.chat.title}</b>, you must join our channel first.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
    except:
        pass # User blocked bot or privacy settings

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_forcejoin":
        await query.message.reply_text("<b>How to Setup:</b>\n1. Make Bot Admin in Group & Channel.\n2. In Group, type: <code>/link CHANNEL_ID</code>", parse_mode=ParseMode.HTML)
        return

    if "chk_" in query.data:
        _, group_id, channel_id = query.data.split("_")
        try:
            # Check Membership
            member = await context.bot.get_chat_member(int(channel_id), query.from_user.id)
            if member.status in ['member', 'administrator', 'creator']:
                await context.bot.approve_chat_join_request(int(group_id), query.from_user.id)
                await query.message.edit_text("✅ <b>Approved!</b> You can now chat in the group.", parse_mode=ParseMode.HTML)
            else:
                await query.answer("❌ You haven't joined yet! Please join first.", show_alert=True)
        except Exception as e:
            await query.message.edit_text(f"⚠️ Error: Bot not admin or request expired.\n{e}")

# --- MASTER MESSAGE HANDLER (CORE LOGIC) ---

async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    # 1. Update Active Group List (for Broadcast/News)
    if chat_type != 'private':
        active_groups_col.update_one({'group_id': chat_id}, {'$set': {'group_id': chat_id}}, upsert=True)

    text = (msg.text or msg.caption or "").lower()
    
    # 2. SECURITY CHECK (Skip for Admins)
    is_sender_admin = False
    if user:
        is_sender_admin = await is_admin(chat_id, user.id, context)

    if user and not is_sender_admin and chat_type != 'private':
        violation_found = False
        reason = ""

        # A. Link Detection (Regex)
        if re.search(r"(https?://|t\.me/|www\.|bit\.ly)", text):
            violation_found = True
            reason = "Link Detected"
        
        # B. Bad Words
        elif any(w in text for w in BAD_WORDS):
            violation_found = True
            reason = "Bad Language"
            
        # C. Selling Keywords
        elif any(w in text for w in SELLING_KEYWORDS):
            violation_found = True
            reason = "Spam/Selling"

        if violation_found:
            print(f"🚨 Violation ({reason}) by {user.first_name} in Chat {chat_id}")
            try:
                await msg.delete()
                is_banned, warn_msg = await add_warning(user.id, chat_id, context)
                
                # Send Warning and delete it after 5 sec
                sent_w = await context.bot.send_message(chat_id, f"{user.mention_html()} {warn_msg}", parse_mode=ParseMode.HTML)
                await asyncio.sleep(5)
                await sent_w.delete()
                return # Stop processing
            except Exception as e:
                print(f"❌ FAILED TO DELETE: Bot is not Admin or Permission missing. Error: {e}")
                return

    # 3. AI REPLY LOGIC
    should_reply = False
    
    if chat_type == 'private':
        should_reply = True
    elif getattr(msg.reply_to_message, 'from_user', None) and msg.reply_to_message.from_user.id == context.bot.id:
        should_reply = True
    elif "?" in text or "explain" in text or "solve" in text or "ssc" in text or "exam" in text:
        should_reply = True
    elif msg.photo:
        should_reply = True # Always scan photos

    if should_reply:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        print(f"🤖 AI Processing: {text[:30]}...")
        
        response_text = ""
        try:
            # Handle Image
            if msg.photo:
                photo_file = await msg.photo[-1].get_file()
                path = f"temp_{user.id}.jpg"
                await photo_file.download_to_drive(path)
                
                img = Image.open(path)
                response_text = await get_ai_response(msg.caption or "Analyze this image.", image=img)
                if os.path.exists(path): os.remove(path)
            
            # Handle Text
            elif text:
                # Group में बहुत छोटे मैसेज पर रिप्लाई न करे (जैसे "Hi", "Ok")
                if chat_type != 'private' and len(text) < 4: return
                response_text = await get_ai_response(text)
                
        except Exception as e:
            print(f"❌ AI Error: {traceback.format_exc()}")
            response_text = "⚠️ Internal AI Error. Please check API Key."

        # Process Response
        if response_text == "VIOLATION_DETECTED":
            try: await msg.delete()
            except: pass
            await context.bot.send_message(chat_id, f"🔞 <b>NSFW Content Blocked!</b> {user.mention_html()}", parse_mode=ParseMode.HTML)
        
        elif response_text:
            try:
                # Try sending with Markdown (Bold/Lists support)
                await msg.reply_text(f"💡 <b>Answer:</b>\n\n{response_text}", parse_mode=ParseMode.MARKDOWN)
            except:
                # Fallback to plain text if Markdown fails
                await msg.reply_text(f"💡 <b>Answer:</b>\n\n{response_text}")
