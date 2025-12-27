# database.py
from pymongo import MongoClient
from config import MONGO_URI

try:
    client = MongoClient(MONGO_URI)
    db = client['UltimateBotDB']
    
    # Collections (Tables)
    group_settings_col = db['group_settings']  # Force Join Settings
    active_groups_col = db['active_groups']    # List of all groups (for News/Broadcast)
    learned_spam_col = db['learned_spam']      # AI learned spam
    whitelist_col = db['whitelist']            # Allowed words
    warnings_col = db['user_warnings']         # User violations
    system_col = db['system_metadata']         # Stores last news link
    
    print("✅ Database Connected Successfully!")

except Exception as e:
    print(f"❌ Database Connection Error: {e}")
  
