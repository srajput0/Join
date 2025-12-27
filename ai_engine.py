import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from config import GEMINI_API_KEY

# API Key Validation
if not GEMINI_API_KEY:
    print("❌ ERROR: API Key Missing in config.py")

genai.configure(api_key=GEMINI_API_KEY)

# 👇 Changed model to 'gemini-pro' (Most Stable) to fix 404 Error
model = genai.GenerativeModel('gemini-pro')

SYSTEM_PROMPT = "You are ExamGuard. Answer in Hindi or English as asked. Keep it short."

# Security Settings
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

async def get_ai_response(text_prompt, image=None):
    try:
        # Note: Gemini Pro doesn't support images directly in free tier easily, 
        # so for text we use this. If image needed, we handle separately.
        if image:
            # Fallback for image (Vision model)
            vision_model = genai.GenerativeModel('gemini-pro-vision')
            response = vision_model.generate_content([text_prompt, image], safety_settings=SAFETY_SETTINGS)
        else:
            response = model.generate_content(SYSTEM_PROMPT + "\nQuery: " + text_prompt, safety_settings=SAFETY_SETTINGS)
        
        if response.prompt_feedback.block_reason:
            return "VIOLATION_DETECTED"
        return response.text
    except Exception as e:
        # Clean Error Message
        if "404" in str(e): return "⚠️ Server Error: Model not found. Update library."
        if "API key" in str(e): return "⚠️ API Key Error. Check config.py."
        return ""

async def get_translation(text):
    try:
        response = model.generate_content(f"Translate to Hindi:\n{text}")
        return response.text
    except: return "Translation Failed."
