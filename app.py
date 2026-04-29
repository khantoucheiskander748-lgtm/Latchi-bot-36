import os
from flask import Flask, jsonify

app = Flask(__name__)

# قراءة المتغيرات من Environment Variables
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_COOKIES = os.getenv("QUOTEX_COOKIES")
QUOTEX_TOKEN = os.getenv("QUOTEX_TOKEN")
QUOTEX_USER_AGENT = os.getenv("QUOTEX_USER_AGENT")

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "telegram_api_id": TELEGRAM_API_ID,
        "telegram_api_hash": TELEGRAM_API_HASH,
        "telegram_channel": TELEGRAM_CHANNEL,
        "quotex_email": QUOTEX_EMAIL
    })
