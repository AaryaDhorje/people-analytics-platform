"""Demo bearer-token authentication.

This is **not** real authentication and the README says so plainly. There is one
hardcoded token, no users, no sessions, no expiry, no revocation. It exists so the
deployed API is not wide open to the internet, and so the Loom can say "auth is a
single demo token, deliberately, because the interesting work was elsewhere."

CLAUDE.md forbids going further: "Do not add authentication beyond the existing demo
token." Anything more would burn hours that belong to the metrics.

Two things are still done properly, because they cost nothing:

- **Constant-time comparison.** `==` on a secret leaks its length and prefix through
  timing. `secrets.compare_digest` does not. The habit matters more than this token.
- **`/health` stays open.** Render polls it during cold start and would fail a
  deployment if it 401'd, and the frontend uses it to distinguish "API is waking up"
  from "API rejected me".
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

#: `auto_error=False` so a missing header reaches our handler and produces a message
#: explaining what to send, rather than FastAPI's bare 403.
_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="DemoBearer",
    description="Single demo token. Send as `Authorization: Bearer <token>`.",
)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def require_demo_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)],
) -> str:
    """Reject anything that is not the configured demo token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token. Send 'Authorization: Bearer <token>'.",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if not secrets.compare_digest(credentials.credentials, settings.demo_bearer_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers=_UNAUTHORIZED_HEADERS,
        )

    return credentials.credentials


#: Attached to every metric router at registration, so a new route cannot be added
#: unprotected by forgetting a decorator.
DemoAuth = Depends(require_demo_token)
