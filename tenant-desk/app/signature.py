"""Check that a webhook call really came from Meta.

Meta signs every POST with our app secret. The header looks like:
    X-Hub-Signature-256: sha256=<hex HMAC-SHA256 of the raw body>
We compute the same value and compare. The raw body must be used
exactly as received (before JSON parsing), or the hash will not match.
"""
import hashlib
import hmac

PREFIX = "sha256="


def compute_signature(raw_body, app_secret):
    """Return the header value Meta would send for this body."""
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return PREFIX + digest


def verify_signature(raw_body, header_value, app_secret):
    """Return True only if the header matches the body and secret."""
    if not header_value or not app_secret:
        return False
    if not header_value.startswith(PREFIX):
        return False
    expected = compute_signature(raw_body, app_secret)
    # compare_digest takes the same time for any input, so an attacker
    # cannot guess the signature one character at a time.
    return hmac.compare_digest(expected, header_value)
