from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Response
from jwt import InvalidTokenError, decode, encode

from app.config import Settings, get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_token(user_id: str, settings: Settings | None = None) -> str:
    current = settings or get_settings()
    expires = datetime.now(timezone.utc) + timedelta(seconds=current.jwt_ttl_seconds)
    return encode({"sub": user_id, "exp": expires}, current.jwt_secret, algorithm="HS256")


def read_token(token: str, settings: Settings | None = None) -> str | None:
    current = settings or get_settings()
    try:
        payload = decode(token, current.jwt_secret, algorithms=["HS256"])
    except InvalidTokenError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        return None
    return subject


def set_session_cookie(response: Response, user_id: str, settings: Settings | None = None) -> None:
    current = settings or get_settings()
    response.set_cookie(
        key=current.cookie_name,
        value=create_token(user_id, current),
        httponly=True,
        secure=current.cookie_secure,
        samesite=current.cookie_samesite,
        max_age=current.jwt_ttl_seconds,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings | None = None) -> None:
    current = settings or get_settings()
    response.delete_cookie(key=current.cookie_name, path="/")
