from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # السماح لجميع المواقع بالوصول

@app.route("/")
def home():
    return jsonify({
        "quotex_email": os.getenv("QUOTEX_EMAIL"),
        "status": "running",
        "telegram_api_hash": os.getenv("TELEGRAM_API_HASH"),
        "telegram_api_id": int(os.getenv("TELEGRAM_API_ID")),
        "telegram_channel": os.getenv("TELEGRAM_CHANNEL")
    })
