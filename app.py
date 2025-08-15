from zoneinfo import ZoneInfo
from flask import Flask, request

# ===== Telegram =====
TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"
# Часовой пояс: можно поменять переменной окружения TZ (например, Europe/Moscow)

# ===== OpenAI =====
from openai import OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # можно поставить gpt-5-mini, если есть доступ
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "You are a helpful assistant. Reply in Russian if the user speaks Russian.")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Часовой пояс для отсчёта до НГ
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Minsk"))

app = Flask(__name__)
@@ -33,11 +43,6 @@

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
@@ -60,6 +65,26 @@
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
@@ -71,7 +96,7 @@
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")  # private | group | supergroup | channel
    text = message.get("text", "") or ""
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    print("UPDATE:", update, flush=True)
@@ -94,14 +119,28 @@
        })
        return "ok"

    # 3) Базовый ответ в приватке (как раньше)
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
        reply = "Нецензурная лексика не приветствуется." if has_profanity(text) else f"Ты написал: {text}"
        reply = f"Ты написал: {text}" if text else "Привет! Напиши что-нибудь."
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    # локальный запуск (на Railway нас запускает gunicorn)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # локальный запуск (на Railway нас запускает gunicorn)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
