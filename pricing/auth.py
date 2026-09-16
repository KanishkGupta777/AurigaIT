"""
Minimal session-token auth for the admin portal.

IMPORTANT: this is demo-grade auth for an assessment project, not
production security. Real systems would hash passwords, use a proper
secrets store, expire/rotate tokens, and use HTTPS-only cookies. Here the
credentials are intentionally simple per the requirement (both "1234"),
kept in one place so they're easy to point out/justify in REASONING.md.
"""
import os
import secrets
import time

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "1234")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

_SESSION_TTL_SECONDS = 60 * 60 * 4  # 4 hours
_sessions = {}  # token -> expiry epoch seconds


def login(username: str, password: str):
    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return None
    token = secrets.token_urlsafe(24)
    _sessions[token] = time.time() + _SESSION_TTL_SECONDS
    return token


def is_valid(token: str) -> bool:
    if not token or token not in _sessions:
        return False
    if _sessions[token] < time.time():
        del _sessions[token]
        return False
    return True


def logout(token: str):
    _sessions.pop(token, None)
