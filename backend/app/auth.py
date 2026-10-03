"""Supabase access token verification; roles are read only from app_metadata."""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .errors import AppError

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    """Verified Supabase identity and trusted application role."""

    id: UUID
    email: str
    role: str = "user"


@lru_cache(maxsize=8)
def jwks_client(url: str) -> jwt.PyJWKClient:
    """Cache public signing keys for five minutes and refresh for unknown key IDs."""
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", timeout=3, lifespan=300)


def verify_token(token: str) -> User:
    """Verify signature, issuer, audience, expiry and subject before authorizing."""
    url = settings.supabase_url.rstrip("/")
    if not url:
        raise AppError(401, "UNAUTHORIZED", "Brak konfiguracji uwierzytelniania")
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
        options = {"require": ["exp", "iat", "sub", "iss", "aud"]}
        if algorithm in ("ES256", "RS256"):
            key = jwks_client(url).get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["ES256", "RS256"],
                                issuer=f"{url}/auth/v1", audience="authenticated", options=options)
            metadata = claims.get("app_metadata", {})
            email = claims.get("email", "")
        elif algorithm == "HS256":
            # Legacy symmetric tokens cannot be verified with public JWKS.
            # Auth validates their signature; never trust a local unverified role.
            api_key = settings.supabase_anon_key.get_secret_value()
            if not api_key:
                raise ValueError("Auth API key is missing")
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{url}/auth/v1/user", headers={"apikey": api_key, "Authorization": f"Bearer {token}"})
            if response.status_code != 200:
                raise ValueError("Auth rejected token")
            verified = response.json()
            claims = jwt.decode(token, options={**options, "verify_signature": False,
                                "verify_exp": True, "verify_iat": True, "verify_nbf": True,
                                "verify_iss": True, "verify_aud": True},
                                issuer=f"{url}/auth/v1", audience="authenticated")
            if claims["sub"] != verified["id"]:
                raise ValueError("Subject mismatch")
            metadata = verified.get("app_metadata", {})
            email = verified.get("email", "")
        else:
            raise ValueError("Unsupported algorithm")
        if claims.get("role") != "authenticated":
            raise ValueError("Not a user token")
        return User(UUID(claims["sub"]), email, "admin" if metadata.get("role") == "admin" else "user")
    except (jwt.PyJWTError, ValueError, KeyError, TypeError, AttributeError, httpx.HTTPError):
        raise AppError(401, "UNAUTHORIZED", "Brak lub nieważny token") from None


def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User | None:
    """Allow anonymous reads; reject a supplied but invalid token."""
    return verify_token(credentials.credentials) if credentials else None


def require_user(user: User | None = Depends(optional_user)) -> User:
    """Require a verified user for writes and profile access."""
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "Wymagane logowanie")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """Require the trusted admin role for moderation."""
    if user.role != "admin":
        raise AppError(403, "FORBIDDEN", "Wymagane uprawnienia administratora")
    return user
