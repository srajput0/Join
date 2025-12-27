

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from config import GEMINI_API_KEY

# API Key Check
if not GEMINI_API_KEY or "YOUR_GEMINI" in GEMINI_API_KEY:
    print("❌ CRITICAL ERROR: API Key config.py में नहीं डाली गई है!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = """
You are 'ExamGuard', a strict but helpful Study Assistant.
1. Answer strictly in English.
2. For Math/Science: Solve step-by-step.
3. Ignore casual "Hi/Hello" unless asked a question.
"""

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
        
        # Check Safety Block
        if response.prompt_feedback.block_reason:
            return "VIOLATION_DETECTED"
            
        return response.text if response.text else "⚠️ Error: Empty response from AI."

    except Exception as e:
        error_msg = str(e)
        if "API_KEY_INVALID" in error_msg or "400" in error_msg:
            return "⚠️ **CRITICAL:** API Key is Invalid. Check config.py!"
        if "safety" in error_msg.lower():
            return "VIOLATION_DETECTED"
        return "" # Return empty to stay silent on minor errors

async def get_translation(text):
    try:
        prompt = f"Translate this text to Hindi (Devanagari script). Just give the translation:\n\n'{text}'"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Translation Failed. (Check API Key)\nError: {str(e)[:50]}"
