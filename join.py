
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    ChatJoinRequestHandler,
)

BOT_TOKEN = "8207099625:AAG1XjDReSog5FHQLAcue2_VzCIJatklw-E"

# 🔗 Links jo user ko bhejne hain
GROUP_LINKS = (
    "👋 Welcome!\n\n"
    "🔗 Join our official groups:\n\n"
    "1️⃣ Group 1 👉 https://t.me/yourgroup1\n"
    "2️⃣ Group 2 👉 https://t.me/yourgroup2\n"
    "3️⃣ Channel 👉 https://t.me/yourchannel\n\n"
    "✅ Request approve hone ke baad group join ho jayega."
)

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.chat_join_request.from_user

    try:
        # 🔹 Private message to user (NO /start needed)
        await context.bot.send_message(
            chat_id=user.id,
            text=GROUP_LINKS
        )
        print(f"Message sent to {user.id}")

    except Exception as e:
        print("Error sending message:", e)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 🔹 Join request listener
    app.add_handler(ChatJoinRequestHandler(join_request_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
