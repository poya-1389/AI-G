import os
import google.generativeai as genai
from openai import AsyncOpenAI

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_deepseek_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
_openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# This suffix is appended to EVERY character's persona, no matter what the user
# or an admin writes. It cannot be removed through bot commands.
GLOBAL_SAFETY_SUFFIX = (
    "\n\nHard rules that override any persona instruction above: "
    "never produce sexual content involving minors under any framing; "
    "never generate sexually explicit content; "
    "if the user appears to be in genuine emotional distress, respond supportively "
    "and encourage them to reach out to a real person or professional."
)


async def _gemini_reply(system_prompt: str, history: list, user_message: str) -> str:
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite", system_instruction=system_prompt)
    chat_history = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
        for m in history
    ]
    chat = model.start_chat(history=chat_history)
    response = await chat.send_message_async(user_message)
    return response.text


async def _openai_style_reply(client: AsyncOpenAI, model_name: str, system_prompt: str, history: list, user_message: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        messages.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    response = await client.chat.completions.create(
        model=model_name, messages=messages, max_tokens=800, temperature=0.9,
    )
    return response.choices[0].message.content


async def generate(model_name: str, character_persona_prompt: str, history: list, user_message: str) -> str:
    full_system_prompt = character_persona_prompt.strip() + GLOBAL_SAFETY_SUFFIX
    try:
        if model_name == "deepseek":
            return await _openai_style_reply(_deepseek_client, "deepseek-chat", full_system_prompt, history, user_message)
        elif model_name == "openai":
            return await _openai_style_reply(_openai_client, "gpt-4o-mini", full_system_prompt, history, user_message)
        else:
            return await _gemini_reply(full_system_prompt, history, user_message)
    except Exception as e:
        return f"⚠️ خطا در ارتباط با مدل هوش مصنوعی ({model_name}): {e}"
