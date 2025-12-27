# main.py
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatJoinRequestHandler, filters
from telegram.constants import ParseMode
from config import BOT_TOKEN
from news_checker import get_latest_exam_news
from database import active_groups_col

from handlers import (
    start, link_channel_command, callback_handler, 
    join_request_handler, master_message_handler,
    translate_command, stats_command, broadcast_alert
)

# --- AUTO NEWS LOOP ---
async def news_loop(app):
    print("🌍 News System Started...")
    while True:
        try:
            data = get_latest_exam_news()
            if data:
                title, link = data
                msg = f"🚨 <b>EXAM UPDATE</b> 🚨\n\n📰 <b>{title}</b>\n🔗 <a href='{link}'>Read More</a>"
                
                groups = active_groups_col.find({})
                for g in groups:
                    try:
                        await app.bot.send_message(g['group_id'], msg, parse_mode=ParseMode.HTML)
                        await asyncio.sleep(0.1)
                    except:
                        active_groups_col.delete_one({'group_id': g['group_id']})
                print(f"✅ News sent: {title}")
        except Exception as e: print(f"News Loop Error: {e}")
        await asyncio.sleep(900) # Check every 15 mins

def main():
    print("🚀 Bot Starting...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_channel_command))
    app.add_handler(CommandHandler("tr", translate_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_alert))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.LEFT_CHAT_MEMBER, master_message_handler))

    # Background Task
    loop = asyncio.get_event_loop()
    loop.create_task(news_loop(app))

    print("✅ Online!")
    app.run_polling()

if __name__ == "__main__":
    main()
  
