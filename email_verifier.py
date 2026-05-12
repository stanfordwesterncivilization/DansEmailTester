"""
DansEmailTester - Email Verification Engine
Faithful reverse-engineering of the original emailtester.com (2010s) logic.
Uses: dnspython, smtplib (stdlib), socket (stdlib)
"""
import re
import smtplib
import socket
import random
import string
import time
import logging
from typing import Optional

try:
    import dns.resolver
    import dns.exception
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────────────────
SMTP_TIMEOUT     = 5           # seconds per connection attempt
EHLO_DOMAIN      = "danstester.local"
MAIL_FROM        = f"verify@{EHLO_DOMAIN}"
CONNECT_RETRIES  = 1

# Disposable / throwaway email domains (abridged canonical list)
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net",
    "guerrillamail.org", "guerrillamail.de", "guerrillamail.info",
    "guerrillamailblock.com", "grr.la", "sharklasers.com", "spam4.me",
    "trashmail.com", "trashmail.at", "trashmail.io", "trashmail.me",
    "trashmail.net", "yopmail.com", "yopmail.fr", "cool.fr.nf",
    "jetable.fr.nf", "nospam.ze.tc", "nomail.xl.cx", "mega.zik.dj",
    "speed.1s.fr", "courriel.fr.nf", "moncourrier.fr.nf",
    "monemail.fr.nf", "monmail.fr.nf",
    "10minutemail.com", "10minutemail.net", "10minutemail.org",
    "10minutemail.co.uk", "20minutemail.com",
    "throwam.com", "throwam.net", "dispostable.com", "fakeinbox.com",
    "mailnull.com", "spamgourmet.com", "spamgourmet.org", "spamgourmet.net",
    "maildrop.cc", "mailnesia.com",
    "tempmail.com", "tempmail.net", "tempinbox.com", "tempr.email",
    "temp-mail.org", "tmpmail.net", "tmpmail.org",
    "getairmail.com", "filzmail.com",
    "spamfree24.org", "spamfree24.de", "spamfree24.eu",
    "spamfree24.info", "spamfree24.net",
    "spamgob.com", "spamgob.net", "spam.la", "spamcorner.com",
    "anonymbox.com", "discard.email", "cfl.fr", "no-spam.ws",
    "notmailinator.com", "safetymail.info",
}

# Role-based prefixes that indicate non-personal addresses
ROLE_PREFIXES = {
    "info", "sales", "support", "admin", "administrator", "help",
    "contact", "noreply", "no-reply", "donotreply", "do-not-reply",
    "marketing", "billing", "accounts", "office", "mail", "email",
    "hello", "hi", "team", "abuse", "postmaster", "webmaster",
    "hostmaster", "security", "privacy", "legal", "hr", "jobs",
    "careers", "press", "media", "pr", "feedback", "service",
    "services", "newsletter", "news", "notifications", "alerts",
    "system", "root", "bounce", "bounces", "mailer-daemon",
}

# SMTP response text patterns that indicate catch-all or policy blocks
CATCHALL_PHRASES = [
    "verification not allowed", "policy violation", "relay access denied",
    "we do not accept", "anti-spam", "blocked", "not available",
]
GREYLISTING_PHRASES = [
    "greylisted", "greylist", "try again later", "temporary", "come back later",
]

# ─── Helpers ────────────────────────────────────────────────────────────────────────────
def _random_address(domain: str) -> str:
    """Generate a random bogus address on the given domain for catch-all detection."""
    rand = "".join(random.choices(string.ascii_lowercase, k=12))
    return f"{rand}@{domain}"


def _validate_syntax(email: str) -> tuple[bool, str]:
    """
    Step 1: Syntax validation.
    Returns (is_valid, reason).
    """
    if not email or len(email) > 254:
        return False, "Email too long or empty"

    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        return False, "Invalid email format"

    local, domain = email.rsplit("@", 1)

    if len(local) > 64:
        return False, "Local part too long (>64 chars)"
    if local.startswith(".") or local.endswith("."):
        return False, "Local part cannot start or end with a dot"
    if ".." in local:
        return False, "Local part contains consecutive dots"

    if len(domain) > 255:
        return False, "Domain too long"
    if domain.startswith("-") or domain.endswith("-"):
        return False, "Domain cannot start or end with a hyphen"
    if ".." in domain:
        return False, "Domain contains consecutive dots"

    return True, "Syntax OK"


def _lookup_mx(domain: str) -> tuple[list[str], str]:
    """
    Step 2: DNS / MX record lookup.
    Returns (sorted_mx_hosts, detail_message).
    """
    if not DNS_AVAILABLE:
        return [domain], "dnspython not installed; using domain as fallback MX"

    mx_hosts = []

    try:
        answers = dns.resolver.resolve(domain, "MX")
        sorted_answers = sorted(answers, key=lambda r: r.preference)
        mx_hosts = [str(r.exchange).rstrip(".") for r in sorted_answers]
        if mx_hosts:
            return mx_hosts, f"Found {len(mx_hosts)} MX record(s)"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        pass

    try:
        dns.resolver.resolve(domain, "A")
        return [domain], "No MX records; using A record fallback"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        pass

    try:
        dns.resolver.resolve(domain, "AAAA")
        return [domain], "No MX/A records; using AAAA record fallback"
    except Exception:
        pass

    return [], "No mail servers found for domain"


def _smtp_probe(mx_host: str, email: str) -> tuple[int, str]:
    """
    Attempt a single SMTP RCPT TO probe against mx_host for email.
    Never delivers mail — sends RSET/QUIT after RCPT TO.
    """
    try:
        with smtplib.SMTP(timeout=SMTP_TIMEOUT) as smtp:
            smtp.connect(mx_host, 25)
            try:
                smtp.ehlo(EHLO_DOMAIN)
            except smtplib.SMTPHeloError:
                smtp.helo(EHLO_DOMAIN)

            code, msg = smtp.docmd(f"MAIL FROM:<{MAIL_FROM}>")
            if code not in (200, 250, 251):
                return code, f"MAIL FROM rejected: {msg.decode(errors='replace')}"

            code, msg = smtp.docmd(f"RCPT TO:<{email}>")
            response_text = msg.decode(errors="replace")

            try:
                smtp.docmd("RSET")
            except Exception:
                pass

            return code, response_text

    except socket.timeout:
        return 408, "Connection timed out"
    except ConnectionRefusedError:
        return 421, "Connection refused on port 25"
    except smtplib.SMTPConnectError as e:
        return 421, f"SMTP connect error: {e}"
    except smtplib.SMTPServerDisconnected:
        return 421, "Server disconnected unexpectedly"
    except OSError as e:
        return 421, f"Network error: {e}"
    except Exception as e:
        return 421, f"Unexpected error: {e}"


def _classify_result(
    real_code: int, real_msg: str,
    catchall_code: int, catchall_msg: str,
) -> tuple[str, str]:
    """
    Step 3 classification:
      GREEN  : real=250 AND random != 250
      YELLOW : catch-all or probing blocked
      RED    : permanent 5xx failure
      ERROR  : timeouts, 4xx, connection failures
    """
    real_msg_l = real_msg.lower()

    if real_code in (400, 421, 450, 451, 452):
        if any(p in real_msg_l for p in GREYLISTING_PHRASES):
            return "error", f"Greylisted (4xx): {real_msg}"
        return "error", f"Temporary failure ({real_code}): {real_msg}"

    if real_code in (408, 421) and real_code != 250:
        return "error", f"Connection problem ({real_code}): {real_msg}"

    if 500 <= real_code <= 599:
        return "invalid", f"Rejected ({real_code}): {real_msg}"

    if real_code in (250, 251):
        if catchall_code in (250, 251):
            return "unverifiable", (
                f"Server accepts all addresses (catch-all). "
                f"Real: {real_code} '{real_msg}'. "
                f"Random: {catchall_code} '{catchall_msg}'"
            )
        if any(p in real_msg_l for p in CATCHALL_PHRASES):
            return "unverifiable", f"Policy block detected: {real_msg}"
        return "valid", f"RCPT accepted ({real_code}): {real_msg}"

    return "error", f"Unexpected response ({real_code}): {real_msg}"


# ─── Public API ───────────────────────────────────────────────────────────────────────────
def verify_email(email: str) -> dict:
    """Main verification function."""
    result = {
        "email":        email.strip().lower(),
        "status":       "error",
        "color":        "gray",
        "details":      "",
        "syntax_ok":    False,
        "mx_records":   [],
        "smtp_code":    None,
        "smtp_msg":     None,
        "is_disposable": False,
        "is_role_based": False,
        "catch_all":    None,
    }

    email = email.strip().lower()
    result["email"] = email

    syntax_ok, syntax_msg = _validate_syntax(email)
    result["syntax_ok"] = syntax_ok
    if not syntax_ok:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = f"Syntax error: {syntax_msg}"
        return result

    local, domain = email.rsplit("@", 1)

    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable"] = True
    if local in ROLE_PREFIXES:
        result["is_role_based"] = True

    mx_hosts, mx_detail = _lookup_mx(domain)
    result["mx_records"] = mx_hosts
    if not mx_hosts:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = f"No mail servers found for {domain}"
        return result

    real_code = None
    real_msg  = "No response"
    for mx in mx_hosts[:1]:
        code, msg = _smtp_probe(mx, email)
        real_code, real_msg = code, msg

    result["smtp_code"] = real_code
    result["smtp_msg"]  = real_msg

    # Skip catch-all probe if connection already timed out / refused
    if real_code in (408, 421):
        catchall_code, catchall_msg = real_code, real_msg
    else:
        catchall_email = _random_address(domain)
        catchall_code, catchall_msg = _smtp_probe(mx_hosts[0], catchall_email)

    if real_code in (250, 251) and catchall_code in (250, 251):
        result["catch_all"] = True
    elif real_code in (250, 251):
        result["catch_all"] = False

    status, details = _classify_result(real_code, real_msg, catchall_code, catchall_msg)
    result["status"]  = status
    result["details"] = details
    result["color"]   = {"valid":"green","invalid":"red","unverifiable":"yellow","error":"gray"}.get(status, "gray")

    return result


def verify_bulk(email_list: list[str], delay: float = 0.5) -> list[dict]:
    """Verify a list of emails with throttle delay. Returns list of result dicts."""
    seen    = set()
    results = []
    for raw in email_list:
        email = raw.strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        results.append(verify_email(email))
        time.sleep(delay)
    return results


def results_to_csv(results: list[dict]) -> str:
    """Convert bulk results to CSV string."""
    import csv, io
    fieldnames = [
        "email","status","color","details","syntax_ok",
        "mx_records","smtp_code","smtp_msg","is_disposable","is_role_based","catch_all",
    ]
    out    = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        row = dict(r)
        row["mx_records"] = "; ".join(row.get("mx_records", []))
        writer.writerow(row)
    return out.getvalue()


# ─── CLI ───────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python email_verifier.py <email> [email2 ...]")
        sys.exit(1)
    emails = sys.argv[1:]
    if len(emails) == 1:
        print(json.dumps(verify_email(emails[0]), indent=2))
    else:
        print(results_to_csv(verify_bulk(emails)))
