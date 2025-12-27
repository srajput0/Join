# news_checker.py
import feedparser
from database import system_col

# Google News RSS (Targeting Indian Exams)
RSS_URL = "https://news.google.com/rss/search?q=SSC+CGL+OR+UPSC+OR+Railway+Exam+Notification+India+when:1d&hl=en-IN&gl=IN&ceid=IN:en"

def get_latest_exam_news():
    """
    Returns (Title, Link) if new news found, else None.
    """
    try:
        feed = feedparser.parse(RSS_URL)
        if not feed.entries: return None

        latest = feed.entries[0]
        title = latest.title
        link = latest.link
        
        # Check Database to avoid duplicates
        last_sent = system_col.find_one({'type': 'last_news'})
        if last_sent and last_sent.get('link') == link:
            return None 

        # Save new link
        system_col.update_one(
            {'type': 'last_news'}, 
            {'$set': {'link': link, 'title': title}}, 
            upsert=True
        )
        return title, link

    except Exception as e:
        print(f"News Error: {e}")
        return None
      
