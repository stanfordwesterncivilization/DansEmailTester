"""
DansEmailTester - Email Verification Engine
Verifies email addresses via syntax, DNS/MX lookup, and heuristic checks.
(SMTP probe not used — outbound port 25 is blocked on this host.)
Uses: dnspython, socket (stdlib)
"""
import re
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

# ─── Constants ──────────────────────────────────────────────────────────────

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


# ─── Helpers ────────────────────────────────────────────────────────────────

def _validate_syntax(email: str) -> tuple[bool, str]:
    """Syntax validation. Returns (is_valid, reason)."""
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
    DNS / MX record lookup.
    Returns (sorted_mx_hosts, detail_message).
    """
    if not DNS_AVAILABLE:
        # Fall back to basic socket resolution
        try:
            socket.getaddrinfo(domain, None)
            return [domain], "dnspython not installed; domain resolves via DNS"
        except socket.gaierror:
            return [], "Domain does not resolve"

    mx_hosts = []

    try:
        answers = dns.resolver.resolve(domain, "MX")
        sorted_answers = sorted(answers, key=lambda r: r.preference)
        mx_hosts = [str(r.exchange).rstrip(".") for r in sorted_answers]
        if mx_hosts:
            return mx_hosts, f"Found {len(mx_hosts)} MX record(s): {mx_hosts[0]}"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        pass

    try:
        dns.resolver.resolve(domain, "A")
        return [domain], "No MX records; domain has A record (may accept mail)"
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        pass

    try:
        dns.resolver.resolve(domain, "AAAA")
        return [domain], "No MX/A records; domain has AAAA record"
    except Exception:
        pass

    return [], "No mail servers found for domain (NXDOMAIN or no MX/A/AAAA)"


# ─── Public API ─────────────────────────────────────────────────────────────

def verify_email(email: str) -> dict:
    """
    Verify an email address via syntax + DNS/MX checks.
    Returns a result dict with status: valid | invalid | unverifiable | error.
    """
    result = {
        "email":         email.strip().lower(),
        "status":        "error",
        "color":         "gray",
        "details":       "",
        "syntax_ok":     False,
        "mx_records":    [],
        "smtp_code":     None,
        "smtp_msg":      "SMTP probe not performed (port 25 unavailable on this host)",
        "is_disposable": False,
        "is_role_based": False,
        "catch_all":     None,
    }

    email = email.strip().lower()
    result["email"] = email

    # Step 1: Syntax
    syntax_ok, syntax_msg = _validate_syntax(email)
    result["syntax_ok"] = syntax_ok
    if not syntax_ok:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = f"Syntax error: {syntax_msg}"
        return result

    local, domain = email.rsplit("@", 1)

    # Step 2: Heuristic flags
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable"] = True
    if local in ROLE_PREFIXES:
        result["is_role_based"] = True

    # Step 3: DNS / MX lookup
    mx_hosts, mx_detail = _lookup_mx(domain)
    result["mx_records"] = mx_hosts

    if not mx_hosts:
        result["status"]  = "invalid"
        result["color"]   = "red"
        result["details"] = f"No mail servers found for domain '{domain}'"
        return result

    # Step 4: Classify
    if result["is_disposable"]:
        result["status"]  = "unverifiable"
        result["color"]   = "yellow"
        result["details"] = f"Disposable/throwaway domain. {mx_detail}"
    else:
        result["status"]  = "valid"
        result["color"]   = "green"
        result["details"] = f"Domain verified — {mx_detail}"

    return result


def verify_bulk(email_list: list[str], delay: float = 0.1) -> list[dict]:
    """Verify a list of emails. Returns list of result dicts."""
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


# ─── CLI ────────────────────────────────────────────────────────────────────
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
