from fastapi import Header, HTTPException, status
from .config import settings

def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if not settings.api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )
