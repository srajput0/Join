
# ai_engine.py
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = """
You are 'ExamGuard', a helpful Study Assistant.
1. Answer in clear English.
2. Solve Math/Science step-by-step.
3. Be professional and motivating.
"""

# High Security (Block Porn/Hate)
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

async def get_ai_response(text_prompt, image=None):
    try:
        if image:
            response = model.generate_content([SYSTEM_PROMPT, text_prompt, image], safety_settings=SAFETY_SETTINGS)
        else:
            chat = model.start_chat(history=[])
            response = chat.send_message(SYSTEM_PROMPT + "\nUser: " + text_prompt, safety_settings=SAFETY_SETTINGS)
        
        if response.prompt_feedback.block_reason or not response.text:
            return "VIOLATION_DETECTED"
        return response.text
    except Exception as e:
        if "safety" in str(e).lower(): return "VIOLATION_DETECTED"
        return ""

async def get_translation(text):
    try:
        prompt = f"Translate this to Hindi (only translation):\n'{text}'"
        response = model.generate_content(prompt)
        return response.text
    except: return "Translation Failed."
