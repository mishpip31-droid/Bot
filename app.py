import os, requests
from flask import Flask, request

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
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text", "")

    if chat_id:
        reply = f"Ты написал: {text}" if text else "Привет! Напиши что-нибудь."
        requests.get(f"{TG_API}/sendMessage",
                     params={"chat_id": chat_id, "text": reply})

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
