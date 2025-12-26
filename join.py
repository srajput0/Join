
import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ChatJoinRequestHandler, CallbackQueryHandler, CommandHandler, ContextTypes

# ================= CONFIGURATION (इसे भरें) =================
BOT_TOKEN = "8265358758:AAE4xUVVEoKcfLVn-BgPhxa9kx43ATww51s"
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
OWNER_ID = 8177972152
# ============================================================

# Logging
logging.basicConfig(level=logging.ERROR)

# --- DATABASE CONNECTION ---
try:
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client['ProBotMix']
    groups_col = db['groups']
    users_col = db['users']
    print("✅ Bot is Connected to Database!")
except Exception as e:
    print(f"❌ DB Error: {e}")

# --- DB FUNCTIONS ---
async def add_user(user_id, name):
    if not await users_col.find_one({"user_id": user_id}):
        await users_col.insert_one({"user_id": user_id, "name": name})

async def add_channel(group_id, link, title):
    # Add new channel to the list
    new_ch = {"link": link, "title": title}
    await groups_col.update_one(
        {"group_id": group_id},
        {"$addToSet": {"channels": new_ch}},
        upsert=True
    )

async def remove_channel(group_id, title):
    await groups_col.update_one(
        {"group_id": group_id},
        {"$pull": {"channels": {"title": title}}}
    )

async def get_channels(group_id):
    doc = await groups_col.find_one({"group_id": group_id})
    return doc.get("channels", []) if doc else []

# --- COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_user(update.effective_user.id, update.effective_user.first_name)
    await update.message.reply_text(
        "👋 **Pro Bot Active!**\n\n"
        "Commands:\n"
        "• `/add <Link> <Title>` - Add Button\n"
        "• `/remove <Title>` - Remove Button\n"
        "• `/view` - See Settings\n"
        "• `/broadcast <Msg>` - Send Message to All",
        parse_mode='Markdown'
    )

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private": return
    # Usage: /add https://t.me/link ButtonName
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Use: `/add https://t.me/link ButtonName`", parse_mode='Markdown')
        return
    
    link = context.args[0]
    title = " ".join(context.args[1:])
    await add_channel(update.effective_chat.id, link, title)
    await update.message.reply_text(f"✅ Button Added: **{title}**", parse_mode='Markdown')

async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    title = " ".join(context.args)
    await remove_channel(update.effective_chat.id, title)
    await update.message.reply_text(f"🗑️ Removed: **{title}**", parse_mode='Markdown')

async def view_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = await get_channels(update.effective_chat.id)
    if not channels:
        await update.message.reply_text("ℹ️ No buttons set.")
        return
    text = "📋 **Current Buttons:**\n"
    for ch in channels:
        text += f"• [{ch['title']}]({ch['link']})\n"
    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    msg = ' '.join(context.args)
    if not msg: return
    
    status = await update.message.reply_text("🚀 Broadcasting...")
    count = 0
    async for u in users_col.find():
        try:
            await context.bot.send_message(u['user_id'], f"📢 **Announcement:**\n\n{msg}", parse_mode='Markdown')
            count += 1
            await asyncio.sleep(0.1)
        except: pass
    await status.edit_text(f"✅ Sent to {count} users.")

# --- MAIN LOGIC (SCREENSHOT STYLE + AUTO APPROVE) ---

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user = request.from_user
    chat = request.chat
    
    await add_user(user.id, user.first_name)

    channels = await get_channels(chat.id)
    
    # Logic 1: Agar koi button set nahi hai -> Direct Approve
    if not channels:
        try: await context.bot.approve_chat_join_request(chat.id, user.id)
        except: pass
        return

    # Logic 2: Buttons Grid Banana (2 buttons per line)
    keyboard = []
    row = []
    for ch in channels:
        row.append(InlineKeyboardButton(ch['title'], url=ch['link']))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    # Last Verify Button
    keyboard.append([InlineKeyboardButton("Verify & Join ✅", callback_data=f"verify_{chat.id}")])

    # Message Text (Screenshot Style)
    msg_text = (
        "**Hello!! ALL BATCHES AVAILABLE**\n"
        "Your Request Has Been Sent, Wait For Admin's Approval\n\n"
        "👇 **Join These Channels Fast:**"
    )

    try:
        # User ko Message bhejo
        await context.bot.send_message(
            chat_id=user.id,
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        # Logic 3: FAILSAFE (Agar Blocked hai to Auto Approve)
        print(f"⚠️ DM Failed for {user.first_name}. Auto Approving...")
        try:
            await context.bot.approve_chat_join_request(chat.id, user.id)
        except: pass

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data.startswith("verify_"):
        chat_id = int(query.data.split("_")[1])
        try:
            await context.bot.approve_chat_join_request(chat_id, query.from_user.id)
            await query.answer("Approved!")
            await query.edit_message_text("✅ **Approved!** Check the group.")
        except:
            await query.answer("Error or Already Joined")

# --- RUN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("view", view_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🔥 Ultimate Bot Started!")
    app.run_polling()

if __name__ == "__main__":
    main()
