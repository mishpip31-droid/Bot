# Telegram Bot на Railway (Python + Flask)

## Запуск локально
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
export TELEGRAM_TOKEN="ВАШ_ТОКЕН"   # Windows PowerShell: $env:TELEGRAM_TOKEN="..."
python app.py
