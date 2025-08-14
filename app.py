import os, re, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request

TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"
# Часовой пояс: можно поменять переменной окружения TZ (например, Europe/Moscow)
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
    target_year = now.year + 1 if now.month == 1 and now.day == 1 and now.hour == 0 else now.year + (1 if now.month > 1 or (now.month == 1 and now.day > 1) else 0)
    # Корректнее так: если мы уже после 1 января текущего года — берём 1 января следующего
    target_year = now.year + 1 if now >= datetime(now.year, 1, 1, tzinfo=TZ) else now.year
    target = datetime(target_year, 12, 31, 23, 59, 59, tzinfo=TZ).replace(year=target_year+0)  # не критично, просто фиксируем TZ
    # На самом деле считаем до 1 января следующего года 00:00
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
    text = message.get("text", "") or ""
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

    # 3) Базовый ответ в приватке (как раньше)
    if chat_type == "private" and chat_id:
        reply = "Нецензурная лексика не приветствуется." if has_profanity(text) else f"Ты написал: {text}"
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    # локальный запуск (на Railway нас запускает gunicorn)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
