"""FastAPI dependencies, including Supabase Auth verification."""

import asyncio
import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from api.config import get_settings
from api.database import ensure_user

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a cached Supabase client using the service key."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials not configured",
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Verify the Supabase JWT and return the caller's user id.

    This is the first layer of security, ahead of Row-Level Security at the
    database level.
    """
    settings = get_settings()

    if settings.dev_auth_enabled:
        logger.warning(
            "[auth] DEV AUTH BYPASS ACTIVE — every request is user %s. "
            "Never enable DEV_AUTH_USER_ID in production.",
            settings.dev_auth_user_id,
        )
        await ensure_user(settings.dev_auth_user_id, settings.dev_auth_user_email)
        return settings.dev_auth_user_id

    if not credentials or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured",
        )

    token = credentials.credentials

    try:
        client = create_client(settings.supabase_url, settings.supabase_key)
        # supabase-py's auth client is synchronous — keep it off the event loop.
        user_resp = await asyncio.to_thread(client.auth.get_user, token)
    except Exception as exc:  # network / SDK failure
        logger.warning("[auth] token verification failed: %s", exc)
        raise _unauthorized("Invalid authentication credentials") from exc

    user = getattr(user_resp, "user", None)
    if user is None or not getattr(user, "id", None):
        raise _unauthorized("Invalid or expired authentication token")

    await ensure_user(user.id, getattr(user, "email", None))
    return user.id
