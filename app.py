from flask import Flask, jsonify
import bot

app = Flask(__name__)

@app.route("/api/start")
def start():
    bot.start_bot()
    return jsonify(bot.state.to_dict())

@app.route("/api/stop")
def stop():
    bot.stop_bot()
    return jsonify(bot.state.to_dict())

@app.route("/api/status")
def status():
    return jsonify(bot.state.to_dict())
