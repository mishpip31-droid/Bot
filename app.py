import os, requests
from flask import Flask, request

# === Важно: читаем токен из переменных окружения ===
TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

@app.get("/")
def health():
    return "ok"

@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    chat = (message.get("chat") or {}).get("id")
    text = message.get("text") or ""

    # Логи, чтобы видеть апдейты в Railway → Logs
    print("UPDATE:", update, flush=True)

    if chat:
        reply = f"Ты написал: {text}" if text else "Привет! Напиши что-нибудь."
        requests.get(f"{TG_API}/sendMessage", params={"chat_id": chat, "text": reply})

    return "ok"

if __name__ == "__main__":
    # === Важно: слушаем 0.0.0.0 и порт из переменной PORT ===
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

