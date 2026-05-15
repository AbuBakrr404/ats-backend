"""
deps.py
-------
FastAPI dependencies:
- verify_jwt: extracts and validates the Supabase user token, returns user_id
- get_supabase: returns a Supabase client using the service role key
"""

import jwt
import httpx
from fastapi import Header, HTTPException, status
from supabase import create_client, Client
from .config import settings

# Single Supabase client instance (service role — full access, server-side only)
_supabase: Client = create_client(settings.supabase_url, settings.supabase_service_key)

# Cache the JWKS public key
_jwks_client = jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


def get_supabase() -> Client:
    """Return the service-role Supabase client."""
    return _supabase


def verify_jwt(authorization: str = Header(...)) -> str:
    """
    Verify the Bearer token from the frontend (a Supabase access_token).
    Returns the authenticated user's UUID.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1]

    try:
        # Try RS256 first (newer Supabase projects)
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
    except Exception:
        try:
            # Fall back to HS256 (legacy Supabase projects)
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired — please sign in again",
            )
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            )

    return payload["sub"]