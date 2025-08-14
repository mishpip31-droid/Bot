import os, re, requests
from flask import Flask, request

TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"
app = Flask(__name__)

# --- 1) Словарь нецензурной лексики (добавляй свои варианты/формы) ---
BAD_WORDS = {
    # примеры: рус/англ; пиши в нижнем регистре, без звездочек
    "бляд", "бля", "сука", "хуй", "пизд", "еба", "ебл", "еб*", "мудак",
    "fuck", "shit", "bitch", "asshole", "dick", "fucker", "motherf"
}
# Чтобы матчить по «частям слова» (похоже/цензурировано),
# скомпилируем паттерн: ищем любую подстроку из BAD_WORDS
BAD_RE = re.compile("|".join(re.escape(w).replace(r"\*", ".*") for w in BAD_WORDS), re.IGNORECASE)

def has_profanity(text: str) -> bool:
    if not text:
        return False
    return bool(BAD_RE.search(text.lower()))

@app.get("/")
def health():
    return "ok"

@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")  # "private" | "group" | "supergroup" | "channel"
    text = message.get("text", "")
    msg_id = message.get("message_id")

    print("UPDATE:", update, flush=True)

    # --- 2) Модерация в группах: удаляем сообщение с матом ---
    if chat_id and msg_id and chat_type in ("group", "supergroup") and has_profanity(text):
        # удалить сообщение
        requests.post(f"{TG_API}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id})
        # необязательно: мягкое предупреждение в ответ (можно закомментировать)
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": "Сообщение удалено: нецензурная лексика запрещена.",
            "reply_to_message_id": msg_id
        })
        return "ok"

    # --- 3) Приватный чат: просто отвечаем (или тоже предупреждаем) ---
    if chat_type == "private" and chat_id:
        reply = "Нецензурная лексика не приветствуется." if has_profanity(text) else f"Ты написал: {text}"
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
