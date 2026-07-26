"""FastAPI dependencies, including Supabase Auth verification."""

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client

from api.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_supabase_client() -> Client:
    """Return an authenticated Supabase client using service key."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials not configured",
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify Supabase JWT token and return the user's UUID.

    This enforces the first layer of security before RLS policies
    apply at the database level.
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured",
        )

    try:
        # Create a client using the anon key
        sb_client = create_client(settings.supabase_url, settings.supabase_key)

        # Verify the JWT using the auth API
        user_resp = sb_client.auth.get_user(credentials.credentials)

        if not user_resp or not user_resp.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_resp.user.id

    except Exception as e:
        logger.error(f"Auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
