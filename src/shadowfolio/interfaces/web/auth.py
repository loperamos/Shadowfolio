"""Who is asking: every API request needs a signed-in user, as `Authorization: Bearer <token>` (the token the sign-in
provider gave them), and a request naming a wallet must be its owner's; another user's wallet answers as one that does
not exist. Open to all: the sign-in settings the frontend needs to sign in, and the jobs the system runs for every
wallet (see SPEC.md on protecting them)."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shadowfolio.interfaces.web.errors import wallet_not_found
from shadowfolio.ports.identity import Identity, IdentityUnavailableError
from shadowfolio.usecases.wallets import Wallets

BEARER = "bearer"
UNAUTHORIZED, UNAVAILABLE = 401, 503
CHALLENGE = {"WWW-Authenticate": "Bearer"}
WALLET_PARAM = "wallet_id"
# Paths answered without a user, under the API's prefix.
OPEN_PATHS = frozenset({"/auth/config", "/sync", "/orders/fill"})


class SignInSettings(BaseModel):
    """What the frontend needs to sign users in with the provider; none of it is a secret."""

    provider: str  # e.g. "auth0"
    domain: str
    client_id: str
    audience: str


def sign_in_checks(identity: Identity, wallets: Wallets, api_prefix: str) -> tuple[Callable[[Request], str], Callable[[Request], None]]:
    """`current_user`, the signed-in user's id (for routes that act for them), and `authorize`, which every API route
    runs: it signs the user in, and refuses wallets that are not theirs."""

    def current_user(request: Request) -> str:
        known: str | None = getattr(request.state, "user_id", None)
        if known is not None:
            return known
        try:
            user_id = identity.user_id(_bearer(request.headers.get("authorization")))
        except IdentityUnavailableError as error:
            raise HTTPException(status_code=UNAVAILABLE, detail=str(error)) from error
        if user_id is None:
            raise HTTPException(status_code=UNAUTHORIZED, detail="sign in first", headers=CHALLENGE)
        request.state.user_id = user_id
        return user_id

    def authorize(request: Request) -> None:
        if request.url.path.removeprefix(api_prefix) in OPEN_PATHS:
            return
        user_id = current_user(request)
        wallet_id = request.path_params.get(WALLET_PARAM)
        if wallet_id is None:
            return
        try:
            wallet = wallets.get(UUID(wallet_id))
        except ValueError:
            return  # not a wallet id: the route refuses it
        if wallet is None or wallet.owner_id != user_id:
            raise wallet_not_found()

    return current_user, authorize


def _bearer(header: str | None) -> str | None:
    kind, _, token = (header or "").partition(" ")
    return token.strip() or None if kind.lower() == BEARER else None


def auth_router(sign_in: SignInSettings | None) -> APIRouter:
    router = APIRouter()

    @router.get("/auth/config")
    def sign_in_settings() -> SignInSettings | None:
        """What the frontend needs to sign users in; null when sign-in is not set up."""
        return sign_in

    return router
