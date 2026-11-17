"""FastAPI dependencies: session resolution, CSRF verification, admin guard.

Server-side enforcement only (SECURITY.md): the browser's idea of admin or
ownership is never trusted — every check re-reads DB state per request.

CSRF model: DB-backed session carries its own random csrf_token; mutating
requests must present it via the X-CSRF-Token header (double-submit style).
The cookie never contains the CSRF value, so cross-site form posts cannot
guess it.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as SAMSession

from ..core.config import get_settings
from ..core.database import get_db
from ..models import Session, User
from ..services import auth_service

CSRF_HEADER = "X-CSRF-Token"


def get_request_ip(request: Request) -> str | None:
    client = request.client
    return client.host if client else None


def _resolve_auth(db: SAMSession, request: Request) -> tuple[User, Session]:
    cookie_token = request.cookies.get(get_settings().session_cookie_name)
    user, session_row = auth_service.validate_session(db, cookie_token=cookie_token)
    if user is None or session_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthenticated"},
            headers={"WWW-Authenticate": "MyCloudSession"},
        )
    return user, session_row


def _verify_origin(request: Request) -> None:
    """Reject cross-origin mutations unless explicitly allowed.

    Same-origin requests must work regardless of the CORS allow-list: CORS
    controls cross-origin reads, while CSRF protection only needs to ensure
    a mutation came from this site. The origin is compared with the scheme
    and Host the client actually used (so localhost:8000 and 127.0.0.1:8000
    both work when that is where the app is served).
    """
    origin = request.headers.get("origin")
    if not origin:
        return  # same-origin fetches may omit Origin (older agents)
    host = request.headers.get("host")
    same_origin = (
        host is not None
        and origin == f"{request.url.scheme}://{host}"
    )
    if same_origin or origin in get_settings().cors_origins:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail={"error": "origin_forbidden"}
    )


def get_current_auth(
    request: Request, db: SAMSession = Depends(get_db)
) -> tuple[User, Session]:
    """Read-only-allowed auth dependency (GETs require no CSRF header)."""
    user, session_row = _resolve_auth(db, request)
    auth_service.touch(session_row, get_settings())
    db.commit()
    return user, session_row


def csrf_protected_auth(
    request: Request, db: SAMSession = Depends(get_db)
) -> tuple[User, Session]:
    """Auth dependency for mutating routes: CSRF header + origin check."""
    user, session_row = _resolve_auth(db, request)
    assert request.method in {"POST", "PUT", "PATCH", "DELETE"}, (
        "csrf_protected_auth is for mutating routes only"
    )
    if not auth_service.csrf_matches(session_row, request.headers.get(CSRF_HEADER)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"error": "csrf_token_invalid"}
        )
    _verify_origin(request)
    auth_service.touch(session_row, get_settings())
    db.commit()
    return user, session_row


def get_current_user(auth: tuple[User, Session] = Depends(get_current_auth)) -> User:
    return auth[0]


def csrf_protected_user(
    auth: tuple[User, Session] = Depends(csrf_protected_auth),
) -> User:
    """User for mutating routes (CSRF enforced, user available)."""
    return auth[0]


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"error": "admin_required"}
        )
    return user
