"""
DansEmailTester - Flask Web Application
Wes Anderson-styled email verification tool.
"""
import os
import io
import csv
import json
import time
from flask import (
    Flask, render_template, request,
    jsonify, Response, send_file
)
from email_verifier import verify_email, verify_bulk, results_to_csv

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grand-budapest-hotel-secret")

# Rate limiting (simple in-memory, per-process)
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
        return jsonify({
            "error": "Too many requests. Please slow down.",
            "status": "error"
        }), 429
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"error": "No email provided", "status": "error"}), 400
    result = verify_email(email)
    return jsonify(result)

@app.route("/bulk", methods=["POST"])
def bulk():
    if _rate_limited():
        return jsonify({"error": "Rate limited.", "status": "error"}), 429
    # Accept JSON array or newline-separated text
    content_type = request.content_type or ""
    if "application/json" in content_type:
        data = request.get_json(silent=True) or {}
        emails = data.get("emails", [])
    else:
        raw = request.data.decode("utf-8", errors="replace")
        emails = [line.strip() for line in raw.splitlines() if line.strip()]
    if not emails:
        return jsonify({"error": "No emails provided"}), 400
    if len(emails) > 100:
        return jsonify({"error": "Max 100 emails per bulk request"}), 400
    results = verify_bulk(emails, delay=0.3)
    fmt = request.args.get("format", "json").lower()
    if fmt == "csv":
        csv_data = results_to_csv(results)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=results.csv"}
        )
    return jsonify(results)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "DansEmailTester"})

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
