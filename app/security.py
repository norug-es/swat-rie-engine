from fastapi import Cookie, Header, HTTPException
from .config import settings
from .auth import get_user_by_session

def require_api_key(
    session_id: str | None = Cookie(default=None, alias="rie_session"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    user = get_user_by_session(session_id)
    if user:
        return user
    # Kept for internal workers and backwards-compatible automated clients.
    if x_api_key and settings.api_key and x_api_key == settings.api_key:
        return {"id": "internal", "email": "internal@swat.local"}
    raise HTTPException(status_code=401, detail="login required")
