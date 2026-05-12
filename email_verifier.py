"""
DansEmailTester - Email Verification Engine
Uses Abstract API's Email Reputation endpoint for mailbox-level verification.
"""
import os
import logging
import requests as http

logger = logging.getLogger(__name__)

ABSTRACT_API_KEY = os.environ.get("ABSTRACT_API_KEY", "")
ABSTRACT_API_URL = "https://emailvalidation.abstractapi.com/v1/"


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

    # Map Abstract API fields to our result dict
    result["syntax_ok"]     = data.get("is_valid_format", {}).get("value", False)
    result["is_disposable"] = data.get("is_disposable_email", {}).get("value", False)
    result["is_role_based"] = data.get("is_role_email", {}).get("value", False)
    result["catch_all"]     = data.get("is_catchall_email", {}).get("value", None)

    deliverability = data.get("deliverability", "UNKNOWN")
    is_mx_found    = data.get("is_mx_found", {}).get("value", False)
    quality_score  = data.get("quality_score", "")
    autocorrect    = data.get("autocorrect", "")

    if not result["syntax_ok"]:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Invalid email format"
        if autocorrect:
            result["details"] += f" — did you mean {autocorrect}?"

    elif not is_mx_found:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Domain has no mail servers"

    elif deliverability == "DELIVERABLE":
        result["status"]  = "valid"
        result["color"]   = "green"
        result["details"] = f"Mailbox verified and deliverable (quality score: {quality_score})"

    elif deliverability == "UNDELIVERABLE":
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = "Mailbox does not exist or is not accepting mail"

    elif deliverability == "RISKY":
        result["status"]  = "unverifiable"
        result["color"]   = "yellow"
        parts = ["Risky address"]
        if result["is_disposable"]:
            parts.append("disposable domain")
        if result["catch_all"]:
            parts.append("catch-all mailbox")
        result["details"] = " — ".join(parts) + f" (quality score: {quality_score})"

    else:  # UNKNOWN
        result["status"]  = "unverifiable"
        result["color"]   = "yellow"
        result["details"] = f"Could not confirm mailbox — server did not respond (quality score: {quality_score})"

    return result
