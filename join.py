import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ChatJoinRequestHandler, CallbackQueryHandler, CommandHandler, ContextTypes

# ================= CONFIGURATION (इसे ध्यान से भरें) =================

# 1. अपना बोट टोकन यहाँ डालें
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# 2. MongoDB URL (Atlas से कॉपी करें)
MONGO_URI = "mongodb+srv://username:password@cluster0.mongodb.net/?retryWrites=true&w=majority"

# 3. आपकी टेलीग्राम ID (Owner ID - Broadcast और Stats के लिए)
OWNER_ID = 123456789

# =====================================================================

# Logging Setup (Console ko saaf rakhne ke liye sirf errors dikhayega)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION (MongoDB) ---
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['ProAutoAcceptBot']
    groups_col = db['groups'] # Stores Group Settings
    users_col = db['users']   # Stores Users for Broadcast
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- DATABASE FUNCTIONS ---

async def add_user_db(user_id, name):
    """Broadcast ke liye user save karega"""
    found = await users_col.find_one({"user_id": user_id})
    if not found:
        await users_col.insert_one({"user_id": user_id, "name": name})

async def add_channel_db(group_id, ch_id, ch_link, ch_title):
    """Group me channel add karega"""
    group = await groups_col.find_one({"group_id": group_id})
    new_ch = {"id": ch_id, "link": ch_link, "title": ch_title}
    
    if group:
        # Purana same ID wala channel hata kar naya update karo
        channels = [c for c in group.get("channels", []) if c["id"] != ch_id]
        channels.append(new_ch)
        await groups_col.update_one({"group_id": group_id}, {"$set": {"channels": channels}})
    else:
        await groups_col.insert_one({"group_id": group_id, "channels": [new_ch]})

async def get_channels_db(group_id):
    """Channels ki list layega"""
    group = await groups_col.find_one({"group_id": group_id})
    return group.get("channels", []) if group else []

async def remove_channel_db(group_id, ch_id):
    """Channel remove karega"""
    group = await groups_col.find_one({"group_id": group_id})
    if group:
        channels = [c for c in group.get("channels", []) if c["id"] != ch_id]
        await groups_col.update_one({"group_id": group_id}, {"$set": {"channels": channels}})
        return True
    return False

# --- COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await add_user_db(user.id, user.first_name)

    if chat.type != "private":
        await update.message.reply_text("👋 Bot is Active! DM me for help.")
        return

    text = (
        f"🤖 **Hello {user.first_name}!**\n\n"
        "Main ek **Auto Request Accept Bot** hoon.\n"
        "Main users ko Channels join karwa kar automatically request accept karta hoon.\n\n"
        "📌 **Setup Guide:**\n"
        "1. Mujhe Group me **Admin** banayein.\n"
        "2. Apne Channel me bhi mujhe **Admin** banayein.\n"
        "3. Group me command likhein:\n"
        "`/add <ChannelID> <Link> <Name>`\n\n"
        "Example:\n`/add -10012345678 https://t.me/demo MyChannel`"
    )
    # Add to Group Button
    btn = [[InlineKeyboardButton("➕ Add Me to Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(btn))

async def add_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    args = context.args

    if chat.type == "private":
        await update.message.reply_text("❌ Ye command Group me use karein.")
        return

    # Check Admin
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("🚫 Sirf Admin ye kar sakta hai.")
        return

    if len(args) < 3:
        await update.message.reply_text("⚠️ **Format:** `/add ChannelID Link Name`", parse_mode='Markdown')
        return

    try:
        ch_id = int(args[0])
        ch_link = args[1]
        ch_title = " ".join(args[2:])
        
        await add_channel_db(chat.id, ch_id, ch_link, ch_title)
        await update.message.reply_text(f"✅ **Saved!**\nButton: [{ch_title}]({ch_link}) added.", parse_mode='Markdown', disable_web_page_preview=True)
    except ValueError:
        await update.message.reply_text("❌ Channel ID number honi chahiye.")

async def remove_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    try:
        ch_id = int(context.args[0])
        success = await remove_channel_db(update.effective_chat.id, ch_id)
        if success: await update.message.reply_text("✅ Channel Removed.")
        else: await update.message.reply_text("❌ Not found.")
    except: pass

async def view_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = await get_channels_db(update.effective_chat.id)
    if not channels:
        await update.message.reply_text("ℹ️ No channels set.")
        return
    text = "📋 **Settings:**\n"
    for ch in channels:
        text += f"• {ch['title']} (ID: `{ch['id']}`)\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    msg = ' '.join(context.args)
    if not msg: return
    
    await update.message.reply_text("🚀 Broadcasting...")
    count = 0
    async for u in users_col.find():
        try:
            await context.bot.send_message(u['user_id'], f"📢 **Announcement:**\n\n{msg}", parse_mode='Markdown')
            count += 1
            await asyncio.sleep(0.1)
        except: pass
    await update.message.reply_text(f"✅ Sent to {count} users.")

# --- THE MAIN LOGIC (Buttons & Auto Accept) ---

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab koi Request Bhejta hai"""
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat
    
    # Save user
    await add_user_db(user.id, user.first_name)

    channels = await get_channels_db(chat.id)
    
    # Agar koi channel set nahi hai, to direct approve
    if not channels:
        try: await context.bot.approve_chat_join_request(chat.id, user.id)
        except: pass
        return

    # --- BUTTONS CREATION ---
    keyboard = []
    # Har channel ke liye ek URL Button banayenge
    for ch in channels:
        keyboard.append([InlineKeyboardButton(f"🔔 Join {ch['title']}", url=ch['link'])])
    
    # Verify Button (Isme Group ID hidden hai)
    keyboard.append([InlineKeyboardButton("✅ Maine Join Kar Liya (Verify)", callback_data=f"verify_{chat.id}")])

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"👋 **Namaste {user.first_name}!**\n\n"
                 f"**{chat.title}** me entry lene ke liye, niche diye gaye buttons par click karke channels join karein.\n\n"
                 f"Fir **Verify** button dabayein.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception:
        print(f"DM Failed for {user.first_name} (User blocked bot or privacy settings)")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify Button Dabane Par"""
    query = update.callback_query
    user = query.from_user
    await query.answer("Checking...")

    if query.data.startswith("verify_"):
        group_id = int(query.data.split("_")[1])
        channels = await get_channels_db(group_id)
        
        missing = []
        for ch in channels:
            try:
                member = await context.bot.get_chat_member(ch["id"], user.id)
                if member.status not in ['member', 'creator', 'administrator']:
                    missing.append(ch)
            except:
                # Agar bot channel me admin nahi hai ya koi error aya, to missing maano
                missing.append(ch)

        if not missing:
            # Sab join hai -> Approve
            try:
                await context.bot.approve_chat_join_request(group_id, user.id)
                await query.edit_message_text("✅ **Approved!**\nWelcome to the group! 🎉", parse_mode='Markdown')
                
                # Group me Welcome msg
                try: await context.bot.send_message(group_id, f"👋 Welcome {user.mention_markdown()}!", parse_mode='Markdown')
                except: pass
            
            except Exception as e:
                if "already a member" in str(e):
                    await query.edit_message_text("✅ Aap pehle se group mein hain!")
                else:
                    await query.edit_message_text("❌ Request Expired/Error.")
        else:
            # Kuch missing hai -> Buttons wapas dikhao
            keyboard = []
            for ch in missing:
                keyboard.append([InlineKeyboardButton(f"❌ Join {ch['title']}", url=ch['link'])])
            keyboard.append([InlineKeyboardButton("🔄 Try Verify Again", callback_data=query.data)])
            
            await query.edit_message_text(
                "⚠️ **Join Incomplete!**\nAbhi bhi kuch channels baki hain. Join karke fir try karein:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

# --- MAIN EXECUTION ---

def main():
    print("🤖 Bot Starting...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_channel_cmd))
    app.add_handler(CommandHandler("remove", remove_channel_cmd))
    app.add_handler(CommandHandler("view", view_settings))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Handlers
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🔥 Bot is Running on Vivo V20! Waiting for users...")
    app.run_polling()

if __name__ == "__main__":
    main()
