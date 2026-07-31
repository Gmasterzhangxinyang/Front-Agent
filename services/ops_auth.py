import hmac
import secrets
import time
from dataclasses import dataclass

from config import settings


SESSION_COOKIE_NAME = "front_agent_ops_session"
LOGIN_WINDOW_SECONDS = 5 * 60
MAX_FAILED_LOGINS = 5


@dataclass(frozen=True)
class OpsSession:
    expires_at: float


_sessions: dict[str, OpsSession] = {}
_failed_logins: dict[str, list[float]] = {}


def validate_ops_auth_config() -> None:
    if not settings.ops_admin_username or not settings.ops_admin_password:
        raise RuntimeError(
            "OPS_ADMIN_USERNAME and OPS_ADMIN_PASSWORD are required"
        )


def credentials_valid(username: str, password: str) -> bool:
    configured_username = settings.ops_admin_username
    configured_password = settings.ops_admin_password
    if not configured_username or not configured_password:
        return False
    return hmac.compare_digest(
        username.encode("utf-8"),
        configured_username.encode("utf-8"),
    ) and hmac.compare_digest(
        password.encode("utf-8"),
        configured_password.encode("utf-8"),
    )


def create_session(*, now: float | None = None) -> str:
    timestamp = time.time() if now is None else now
    token = secrets.token_urlsafe(32)
    _sessions[token] = OpsSession(
        expires_at=timestamp + session_max_age_seconds(),
    )
    _prune_sessions(timestamp)
    return token


def session_valid(token: str | None, *, now: float | None = None) -> bool:
    if not token:
        return False
    timestamp = time.time() if now is None else now
    session = _sessions.get(token)
    if session is None:
        return False
    if session.expires_at <= timestamp:
        _sessions.pop(token, None)
        return False
    return True


def revoke_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def session_max_age_seconds() -> int:
    return max(1, settings.ops_session_hours) * 60 * 60


def login_retry_after(client_key: str, *, now: float | None = None) -> int:
    timestamp = time.monotonic() if now is None else now
    attempts = _recent_failed_logins(client_key, timestamp)
    if len(attempts) < MAX_FAILED_LOGINS:
        return 0
    return max(
        1,
        int(LOGIN_WINDOW_SECONDS - (timestamp - attempts[0])),
    )


def record_failed_login(client_key: str, *, now: float | None = None) -> None:
    timestamp = time.monotonic() if now is None else now
    attempts = _recent_failed_logins(client_key, timestamp)
    attempts.append(timestamp)
    _failed_logins[client_key] = attempts


def clear_failed_logins(client_key: str) -> None:
    _failed_logins.pop(client_key, None)


def reset_auth_state() -> None:
    """Clear process-local auth state for tests and controlled restarts."""
    _sessions.clear()
    _failed_logins.clear()


def _recent_failed_logins(client_key: str, now: float) -> list[float]:
    cutoff = now - LOGIN_WINDOW_SECONDS
    attempts = [
        attempt
        for attempt in _failed_logins.get(client_key, [])
        if attempt > cutoff
    ]
    if attempts:
        _failed_logins[client_key] = attempts
    else:
        _failed_logins.pop(client_key, None)
    return attempts


def _prune_sessions(now: float) -> None:
    expired = [
        token
        for token, session in _sessions.items()
        if session.expires_at <= now
    ]
    for token in expired:
        _sessions.pop(token, None)
