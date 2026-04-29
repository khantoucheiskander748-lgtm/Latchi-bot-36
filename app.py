from flask import Flask, jsonify
from flask_cors import CORS
import bot

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "Quotex Bot API"})

@app.route("/api/state")
def api_state():
    return jsonify(bot.state.to_dict())

@app.route("/api/signals")
def api_signals():
    return jsonify(bot.state.signals[-20:])

@app.route("/api/start", methods=["POST"])
def api_start():
    started = bot.start_bot()
    return jsonify({"ok": started, "state": bot.state.to_dict()})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stopped = bot.stop_bot()
    return jsonify({"ok": stopped, "state": bot.state.to_dict()})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    bot.state.reset_stats()
    return jsonify({"ok": True, "state": bot.state.to_dict()})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
