from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings


bearer_scheme = HTTPBearer(
    auto_error=False
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> CurrentUser:
    """
    Resolve identity and role from the bearer token.

    The caller does NOT provide their role in the request body.
    The backend derives it from the configured token.
    """

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    token = credentials.credentials

    if token == settings.analyst_token:
        return CurrentUser(
            user_id="analyst",
            role="analyst",
        )

    if token == settings.reviewer_token:
        return CurrentUser(
            user_id="reviewer",
            role="reviewer",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def require_analyst(
    user: CurrentUser = Depends(
        get_current_user
    ),
) -> CurrentUser:
    if user.role != "analyst":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst permission required.",
        )

    return user


def require_reviewer(
    user: CurrentUser = Depends(
        get_current_user
    ),
) -> CurrentUser:
    if user.role != "reviewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer permission required.",
        )

    return user