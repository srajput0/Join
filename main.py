import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatJoinRequestHandler, filters
from telegram.constants import ParseMode
from config import BOT_TOKEN
from news_checker import get_latest_exam_news
from database import active_groups_col

# Import Handlers from the updated handlers.py
from handlers import (
    start, link_channel_command, callback_handler, 
    join_request_handler, master_message_handler,
    translate_command, stats_command, broadcast_alert
)

# Logging Setup (Error देखने के लिए)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR # सिर्फ Error दिखाएगा ताकि कंसोल साफ़ रहे
)

# --- 🌍 AUTO NEWS LOOP (BACKGROUND TASK) ---
async def news_loop(application: Application):
    """
    यह फंक्शन हर 15 मिनट में न्यूज़ चेक करेगा और ग्रुप्स में भेजेगा।
    """
    print("🌍 Auto-News System Started...")
    while True:
        try:
            # 1. Check for News
            data = get_latest_exam_news()
            
            if data:
                title, link = data
                msg = (
                    f"🚨 <b>OFFICIAL EXAM UPDATE</b> 🚨\n\n"
                    f"📰 <b>{title}</b>\n"
                    f"🔗 <a href='{link}'>Click to Read More</a>\n\n"
                    f"🔔 <i>Bot: ExamGuard Update</i>"
                )

                # 2. Broadcast to all active groups
                groups = active_groups_col.find({})
                count = 0
                
                for g in groups:
                    try:
                        # Send Message
                        await application.bot.send_message(
                            chat_id=g['group_id'], 
                            text=msg, 
                            parse_mode=ParseMode.HTML
                        )
                        count += 1
                        await asyncio.sleep(0.1) # Flood Wait Prevention
                    except Exception:
                        # अगर बोट ग्रुप से किक हो गया, तो डेटाबेस से हटा दें
                        active_groups_col.delete_one({'group_id': g['group_id']})
                
                print(f"✅ News sent to {count} groups: {title}")
            
            else:
                pass # कोई नई खबर नहीं है

        except Exception as e:
            print(f"⚠️ News Loop Error: {e}")

        # 3. Wait for 15 Minutes (900 Seconds)
        await asyncio.sleep(900)

# --- 🚀 STARTUP FUNCTION ---
async def post_init(application: Application):
    # बोट स्टार्ट होते ही बैकग्राउंड में न्यूज़ लूप चलाएं
    asyncio.create_task(news_loop(application))

# --- MAIN EXECUTION ---
def main():
    print("🚀 Ultimate Bot Starting...")
    
    # Application Build with 'post_init' (Fixes Loop Warnings)
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # --- 1. REGISTER HANDLERS ---
    
    # Admin & Utility Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_channel_command))
    app.add_handler(CommandHandler("tr", translate_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_alert))
    
    # Button & Join Request Handlers
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    
    # --- 2. MASTER HANDLER (Security + AI) ---
    # यह सबसे अंत में होना चाहिए ताकि यह टेक्स्ट/फोटो को हैंडल करे
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.LEFT_CHAT_MEMBER, master_message_handler))

    print("✅ Bot is Online! Waiting for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()
