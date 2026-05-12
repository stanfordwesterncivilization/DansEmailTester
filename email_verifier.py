"""
DansEmailTester - Email Verification Engine
Uses Abstract API's Email Reputation endpoint for mailbox-level verification.
"""
import os
import logging
import requests as http

logger = logging.getLogger(__name__)

ABSTRACT_API_KEY = os.environ.get("ABSTRACT_API_KEY", "")
ABSTRACT_API_URL = "https://emailreputation.abstractapi.com/v1/"


def verify_email(email: str) -> dict:
    """Verify an email via Abstract API. Returns a result dict."""
    email = email.strip().lower()

    result = {
        "email":         email,
        "status":        "error",
        "color":         "gray",
        "details":       "",
        "syntax_ok":     False,
        "mx_records":    [],
        "smtp_code":     None,
        "smtp_msg":      None,
        "is_disposable": False,
        "is_role_based": False,
        "catch_all":     None,
    }

    if not ABSTRACT_API_KEY:
        result["details"] = "API key not configured"
        return result

    try:
        resp = http.get(
            ABSTRACT_API_URL,
            params={"api_key": ABSTRACT_API_KEY, "email": email},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except http.exceptions.Timeout:
        result["details"] = "Verification timed out — please try again"
        return result
    except http.exceptions.RequestException as e:
        result["details"] = f"API error: {e}"
        return result

    # Parse Email Reputation API response structure
    deliverability = data.get("email_deliverability", {})
    quality        = data.get("email_quality", {})
    risk           = data.get("email_risk", {})

    is_format_valid = deliverability.get("is_format_valid", False)
    is_mx_valid     = deliverability.get("is_mx_valid", False)
    status          = deliverability.get("status", "unknown").lower()
    mx_records      = deliverability.get("mx_records", [])

    quality_score   = quality.get("score", "")
    is_disposable   = quality.get("is_disposable", False)
    is_catchall     = quality.get("is_catchall", False)
    is_suspicious   = quality.get("is_username_suspicious", False)

    address_risk    = risk.get("address_risk_status", "low").lower()

    result["syntax_ok"]     = is_format_valid
    result["mx_records"]    = mx_records
    result["is_disposable"] = is_disposable
    result["is_role_based"] = is_suspicious
    result["catch_all"]     = is_catchall

    if not is_format_valid:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Invalid email format"
    elif not is_mx_valid:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Domain has no mail servers"
    elif status == "deliverable":
        result["status"]  = "valid"
        result["color"]   = "green"
        result["details"] = f"Mailbox verified and deliverable (quality score: {quality_score})"
    elif status == "undeliverable":
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Mailbox does not exist or is not accepting mail"
    elif status in ("risky", "unknown") or address_risk in ("medium", "high"):
        result["status"]  = "unverifiable"
        result["color"]   = "yellow"
        parts = ["Risky address" if address_risk in ("medium", "high") else "Could not confirm mailbox"]
        if is_disposable: parts.append("disposable domain")
        if is_catchall:   parts.append("catch-all mailbox")
        score_str = f" (quality score: {quality_score})" if quality_score != "" else ""
        result["details"] = " — ".join(parts) + score_str
    else:
        result["status"]  = "unverifiable"
        result["color"]   = "yellow"
        result["details"] = f"Could not confirm mailbox — server did not respond (quality score: {quality_score})"

    return result
