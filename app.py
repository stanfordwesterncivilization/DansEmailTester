"""
DansEmailTester - Flask Web Application
"""
import os
import time
from flask import Flask, render_template, request, jsonify
from email_verifier import verify_email

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grand-budapest-hotel-secret")

# Simple in-memory rate limiter
_request_times: list[float] = []
MAX_REQUESTS_PER_MINUTE = 30

def _rate_limited() -> bool:
    now = time.time()
    global _request_times
    _request_times = [t for t in _request_times if now - t < 60]
    if len(_request_times) >= MAX_REQUESTS_PER_MINUTE:
        return True
    _request_times.append(now)
    return False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/verify", methods=["POST"])
def verify():
    if _rate_limited():
        return jsonify({"error": "Too many requests. Please slow down.", "status": "error"}), 429
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"error": "No email provided", "status": "error"}), 400
    result = verify_email(email)
    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "DansEmailTester"})

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
