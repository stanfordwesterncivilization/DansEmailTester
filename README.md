# Dan's Email Tester

A Flask web app for real-time email verification. Reverse-engineered from the original emailtester.com logic. Wes Anderson / Royal Tenenbaums aesthetic.

## Features

- **Syntax validation** — RFC-compliant format checks
- **DNS / MX lookup** — confirms mail servers exist for the domain
- **SMTP RCPT TO probe** — connects to the mail server without delivering mail
- **Catch-all detection** — sends a random bogus address to check if the server accepts everything
- **Disposable domain flagging** — identifies throwaway email services
- **Role address detection** — flags generic addresses (sales@, info@, support@, etc.)
- **Bulk verification** — up to 100 addresses at once with CSV export

## Status colors

| Color | Status | Meaning |
|-------|--------|---------|
| Green | Valid | MX found, SMTP accepted, not a catch-all |
| Yellow | Unverifiable | Server accepts all addresses or blocks probing |
| Red | Invalid | Permanent rejection or no mail servers found |
| Gray | Error | Timeout or connection failure — try again later |

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

App runs at `http://localhost:5000`.

## Dependencies

```
flask>=3.0.0
dnspython>=2.4.0
gunicorn>=21.0.0
```

## Python API

```python
from email_verifier import verify_email, verify_bulk, results_to_csv

# Single address
result = verify_email("dan@example.com")
# {
#   "email": "dan@example.com",
#   "status": "valid",          # valid | invalid | unverifiable | error
#   "color": "green",           # green | red | yellow | gray
#   "details": "RCPT accepted (250): OK",
#   "syntax_ok": True,
#   "mx_records": ["mail.example.com"],
#   "smtp_code": 250,
#   "smtp_msg": "OK",
#   "is_disposable": False,
#   "is_role_based": False,
#   "catch_all": False
# }

# Bulk verification
results = verify_bulk(["alice@example.com", "bob@domain.net"], delay=0.5)

# Export to CSV
csv_string = results_to_csv(results)
```

## Preview

Open `preview.html` in any browser to see the UI with mock data — no server required.

## Deployment

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

Set `SECFT_KEY` and optionally `FLASK_DEBUG=true` via environment variables.
