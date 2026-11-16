"""How the Auth0 identity checks a signed-in user's token: signed by the tenant (its public keys fetched from its
JWKS address, with the network replaced by a fake transport), for this API, and not expired by our clock."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from shadowfolio.adapters.auth0_identity import Auth0Identity
from shadowfolio.adapters.fixed_clock import FixedClock
from shadowfolio.ports.identity import IdentityUnavailableError

DOMAIN = "tenant.eu.auth0.com"
AUDIENCE = "https://shadowfolio/api"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_ID = "key-1"


def jwks(*keys: tuple[str, Any]) -> dict[str, Any]:
    return {
        "keys": [
            {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": kid, "alg": "RS256", "use": "sig"}
            for kid, key in keys
        ]
    }


def token(key: Any = KEY, kid: str = KEY_ID, **claims: Any) -> str:
    payload = {
        "iss": f"https://{DOMAIN}/",
        "aud": AUDIENCE,
        "sub": "auth0|ana",
        "iat": int((NOW - timedelta(minutes=5)).timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def identity(seen: list[httpx2.Request], keys: list[dict[str, Any]], status: int = 200, clock: FixedClock | None = None) -> Auth0Identity:
    """Answers the n-th JWKS request with keys[n] (the last one from then on)."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, text=json.dumps(keys[min(len(seen), len(keys)) - 1]))

    return Auth0Identity(DOMAIN, AUDIENCE, clock or FixedClock(NOW), transport=httpx2.MockTransport(handler))


def test_a_token_signed_by_the_tenant_for_this_api_gives_its_user() -> None:
    seen: list[httpx2.Request] = []
    users = identity(seen, [jwks((KEY_ID, KEY))])

    assert users.user_id(token()) == "auth0|ana"
    assert users.user_id(token()) == "auth0|ana"
    assert [str(request.url) for request in seen] == [f"https://{DOMAIN}/.well-known/jwks.json"]  # keys fetched once


@pytest.mark.parametrize(
    "bad",
    [
        token(aud="https://another/api"),
        token(iss="https://another.auth0.com/"),
        token(key=OTHER_KEY),
        token(exp=int((NOW - timedelta(seconds=1)).timestamp())),
        "not.a.token",
    ],
)
def test_a_token_from_elsewhere_for_another_api_forged_or_expired_gives_no_user(bad: str) -> None:
    assert identity([], [jwks((KEY_ID, KEY))]).user_id(bad) is None


def test_a_new_signing_key_is_fetched_when_the_tenant_rotates_its_keys() -> None:
    seen: list[httpx2.Request] = []
    users = identity(seen, [jwks((KEY_ID, KEY)), jwks((KEY_ID, KEY), ("key-2", OTHER_KEY))])
    users.user_id(token())

    assert users.user_id(token(key=OTHER_KEY, kid="key-2")) == "auth0|ana"
    assert len(seen) == 2


def test_no_token_gives_no_user_and_asks_nothing() -> None:
    seen: list[httpx2.Request] = []

    assert identity(seen, [jwks((KEY_ID, KEY))]).user_id(None) is None
    assert seen == []


def test_keys_that_cannot_be_fetched_mean_sign_in_is_unavailable() -> None:
    with pytest.raises(IdentityUnavailableError):
        identity([], [{}], status=503).user_id(token())
