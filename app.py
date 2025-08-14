import os, re, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request

# ===== Telegram =====
TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"

# ===== OpenAI =====
from openai import OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # можно поставить gpt-5-mini, если есть доступ
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "You are a helpful assistant. Reply in Russian if the user speaks Russian.")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Часовой пояс для отсчёта до НГ
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Minsk"))

app = Flask(__name__)

# ---------- ФИЛЬТР НЕЦЕНЗУРНЫХ СЛОВ ----------
BAD_WORDS = {
    "бляд", "бля", "сука", "хуй", "пизд", "еба", "ебл", "еб*", "мудак",
    "fuck", "shit", "bitch", "asshole", "dick", "fucker", "motherf"
}
BAD_RE = re.compile("|".join(re.escape(w).replace(r"\*", ".*") for w in BAD_WORDS), re.IGNORECASE)

def has_profanity(text: str) -> bool:
    return bool(text and BAD_RE.search(text.lower()))

# ---------- РАСПОЗНАВАНИЕ ВОПРОСА ПРО НОВЫЙ ГОД ----------
NY_PATTERNS = [
    r"\bсколько\s+(дней|осталось)?\s*до\s+(нов(ого)?\s*год(а)?|нг)\b",
    r"\bдо\s+(нов(ого)?\s*год(а)?|нг)\s*(сколько\s*(осталось)?)?\b",
    r"\bкогда\s+нов(ый|ый)\s*год\b",
]
NY_RE = re.compile("|".join(NY_PATTERNS), re.IGNORECASE)

def is_new_year_query(text: str) -> bool:
    return bool(text and NY_RE.search(text))

def time_to_new_year_str() -> str:
    now = datetime.now(TZ)
    target = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=TZ)
    delta = target - now
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    def plural(n, f1, f2, f5):
        n = abs(n) % 100
        n1 = n % 10
        if 11 <= n <= 19: return f5
        if 1 == n1: return f1
        if 2 <= n1 <= 4: return f2
        return f5

    parts = []
    if days:    parts.append(f"{days} {plural(days,'день','дня','дней')}")
    if hours:   parts.append(f"{hours} {plural(hours,'час','часа','часов')}")
    if minutes: parts.append(f"{minutes} {plural(minutes,'минута','минуты','минут')}")
    if not parts: parts.append("меньше минуты")
    return "До Нового года осталось: " + ", ".join(parts) + f" (часовой пояс: {TZ.key})."

# ---------- GPT-вызов ----------
def ask_gpt(prompt: str) -> str:
    if not client:
        return "⚠️ OPENAI_API_KEY не задан в Variables Railway."
    try:
        # Вариант через Chat Completions (устойчивый и простой)
        # Документация: https://platform.openai.com/docs/api-reference/chat
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=700,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка GPT: {e}"

@app.get("/")
def health():
    return "ok"

@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")  # private | group | supergroup | channel
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    print("UPDATE:", update, flush=True)

    # 1) Модерация: удаляем мат в группах
    if chat_id and msg_id and chat_type in ("group", "supergroup") and has_profanity(text):
        requests.post(f"{TG_API}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id})
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": "Сообщение удалено: запрещена нецензурная лексика.",
        })
        return "ok"

    # 2) Ответ на вопрос про Новый год (в любых чатах)
    if chat_id and is_new_year_query(text):
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": time_to_new_year_str(),
            "reply_to_message_id": msg_id
        })
        return "ok"

    # 3) GPT: команда /gpt <вопрос> (в группе и в приватке)
    if chat_id and (text.lower().startswith("/gpt ") or text.lower() == "/gpt"):
        query = text[4:].strip() or "Привет! Расскажи, что ты умеешь?"
        answer = ask_gpt(query)
        # ограничим длину на всякий случай
        if len(answer) > 3500:
            answer = answer[:3500] + "…"
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": answer,
            "reply_to_message_id": msg_id
        })
        return "ok"

    # 4) Базовый ответ в приватке (эхо)
    if chat_type == "private" and chat_id:
        reply = f"Ты написал: {text}" if text else "Привет! Напиши что-нибудь."
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    # локальный запуск (на Railway нас запускает gunicorn)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
