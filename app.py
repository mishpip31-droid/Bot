import os, re, time, random, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request

# ===== Telegram =====
TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"

# ===== OpenAI (опционально) =====
from openai import OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are a helpful assistant. Reply in Russian if the user speaks Russian."
)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ===== Время =====
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

# ---------- НОВЫЙ ГОД ----------
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
        if n1 == 1: return f1
        if 2 <= n1 <= 4: return f2
        return f5

    parts = []
    if days:    parts.append(f"{days} {plural(days,'день','дня','дней')}")
    if hours:   parts.append(f"{hours} {plural(hours,'час','часа','часов')}")
    if minutes: parts.append(f"{minutes} {plural(minutes,'минута','минуты','минут')}")
    if not parts: parts.append("меньше минуты")
    return "До Нового года осталось: " + ", ".join(parts) + f" (часовой пояс: {TZ.key})."

# ---------- GPT (общая функция) ----------
def ask_gpt(prompt: str) -> str:
    if not client:
        return "⚠️ OPENAI_API_KEY не задан в Variables Railway."
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=120,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Ошибка GPT: {e}"

# ---------- САНТА-ШУТКИ ----------
TRIGGER_PATTERNS = [
    r"\bпривет(,)?\b",
    r"\bскучно\b",
    r"\bчто делаем\b",
    r"\bкак дела\b",
    r"\bшутк|анекдот\b",
    r"\bпраздник|елк|ёлк|нов(ый|ого)\s*год\b",
]
TRIGGER_RE = re.compile("|".join(TRIGGER_PATTERNS), re.IGNORECASE)

JOKE_COOLDOWN_MIN = int(os.environ.get("JOKE_COOLDOWN_MIN", "15"))       # кулдаун на чат для триггерных шуток
RANDOM_JOKE_PROB = float(os.environ.get("RANDOM_JOKE_PROB", "0.10"))     # 10% шанс на любое сообщение
HOURLY_JOKE_INTERVAL_MIN = int(os.environ.get("HOURLY_JOKE_INTERVAL_MIN", "60"))  # «раз в час» на чат

# трекеры времени (секунды unixtime)
last_trigger_joke_at: dict[int, float] = {}   # по триггерам
last_hourly_joke_at:  dict[int, float] = {}   # раз в час
last_random_joke_at:  dict[int, float] = {}   # случайные

CANNED_JOKES = [
    "Почему Санта не пользуется лифтом? Он верит в силу санок! 🎅🛷",
    "Любимый жанр Санты? Хо-хо-хоп! 🎶",
    "Олени не спорят с Сантой — у него всегда последнее «хо-хо»! 🦌",
    "Санта всегда в настроении — у него печеньки на продакшене! 🍪",
    "Санта зовёт оленей на обед: «Хо-хо-хо, к столу!» 🎅",
    "Зима — лучший дресс-код для шубы Санты. ❄️",
    "Санта на спорте: сноуборд — костюм подходит! 🏂",
    "Шутка загружается… 99%… ой, опять подарки в прод! 🎁",
    "Оленя-шутника зовут Хохотун — проверено Сантой! 😄",
    "Главное — не паниковать. Остальное подвезут на санях. 🛷",
]

def gen_santa_joke(username: str | None, context: str | None) -> str:
    if client:
        try:
            prompt = (
                "Скажи ОДНУ очень короткую, добрую и безопасную шутку на русском (до 15 слов) "
                "ОТ ЛИЦА САНТА КЛАУСА. Лёгкий зимний/новогодний вайб, без токсичности и политики. "
                f"Имя пользователя: {username or 'друг'}. Контекст: {(context or '')[:80]}"
            )
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты — Санта Клаус. Шути дружелюбно, коротко, без грубостей."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=60,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text[:200] if text else random.choice(CANNED_JOKES)
        except Exception:
            return random.choice(CANNED_JOKES)
    return random.choice(CANNED_JOKES)

def send_santa_joke(chat_id: int, reply_to: int | None, username: str | None, context_text: str | None):
    joke = gen_santa_joke(username, context_text)
    if not joke:
        return
    payload = {"chat_id": chat_id, "text": joke}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    requests.post(f"{TG_API}/sendMessage", json=payload)

def should_tell_trigger_joke(chat_id: int, text: str) -> bool:
    if not text or not TRIGGER_RE.search(text):
        return False
    now_ts = time.time()
    last_ts = last_trigger_joke_at.get(chat_id, 0)
    if now_ts - last_ts < JOKE_COOLDOWN_MIN * 60:
        return False
    last_trigger_joke_at[chat_id] = now_ts
    return True

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
    username = (message.get("from") or {}).get("first_name")

    print("UPDATE:", update, flush=True)

    # 0) Реакция 👍 на фото (в группах)
    photos = message.get("photo") or []
    if chat_id and msg_id and photos and chat_type in ("group", "supergroup"):
        try:
            requests.post(
                f"{TG_API}/setMessageReaction",
                json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reaction": [ {"type": "emoji", "emoji": "👍"} ],
                },
                timeout=5
            )
        except Exception as e:
            print(f"setMessageReaction error: {e}", flush=True)

    # 1) Модерация мата (в группах)
    if chat_id and msg_id and chat_type in ("group", "supergroup") and has_profanity(text):
        requests.post(f"{TG_API}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id})
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": "Сообщение удалено: запрещена нецензурная лексика.",
        })
        return "ok"

    # 1.1) Санта-шутки по триггерам (в группах, с кулдауном)
    if chat_id and chat_type in ("group", "supergroup") and should_tell_trigger_joke(chat_id, text):
        send_santa_joke(chat_id, msg_id, username, text)

    # 1.2) Дополнительно: «раз в час» ИЛИ 10% случайно (в группах)
    if chat_id and chat_type in ("group", "supergroup"):
        now_ts = time.time()
        # (A) «Раз в час» — не чаще, чем раз в HOURLY_JOKE_INTERVAL_MIN для этого чата
        last_hourly = last_hourly_joke_at.get(chat_id, 0)
        if now_ts - last_hourly >= HOURLY_JOKE_INTERVAL_MIN * 60:
            send_santa_joke(chat_id, None, username, text)
            last_hourly_joke_at[chat_id] = now_ts
        else:
            # (B) Случайная 10% — без спама (не чаще, чем раз в JOKE_COOLDOWN_MIN)
            last_random = last_random_joke_at.get(chat_id, 0)
            if now_ts - last_random >= JOKE_COOLDOWN_MIN * 60 and random.random() < RANDOM_JOKE_PROB:
                send_santa_joke(chat_id, None, username, text)
                last_random_joke_at[chat_id] = now_ts

    # 2) Ответ на вопрос про Новый год
    if chat_id and is_new_year_query(text):
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": time_to_new_year_str(),
            "reply_to_message_id": msg_id
        })
        return "ok"

    # 2.9) /joke — шутка по запросу (Санта-стайл)
    if chat_id and text.lower().strip() == "/joke":
        send_santa_joke(chat_id, msg_id, username, text)
        return "ok"

    # 3) GPT: /gpt ...
    if chat_id and (text.lower().startswith("/gpt ") or text.lower() == "/gpt"):
        query = text[4:].strip() or "Привет! Расскажи, что ты умеешь?"
        answer = ask_gpt(query)
        if len(answer) > 3500:
            answer = answer[:3500] + "…"
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": answer,
            "reply_to_message_id": msg_id
        })
        return "ok"

    # 4) Эхо в приватке
    if chat_type == "private" and chat_id:
        reply = f"Ты написал: {text}" if text else "Привет! Напиши что-нибудь."
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
