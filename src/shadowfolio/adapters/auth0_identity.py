"""Identity from Auth0 (https://auth0.com): a user's access token is a JWT signed by the tenant (RS256).

It is valid when signed with one of the tenant's public keys (fetched from its JWKS address, and fetched again when a
token names a key not seen yet, as when the tenant rotates them), issued by the tenant for this API (its audience), and
not expired by our clock. Its subject ("sub", e.g. "auth0|64f…") is the user id. Only public keys are used: checking
tokens needs no secret.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx2
import jwt

from shadowfolio.ports.clock import Clock
from shadowfolio.ports.identity import Identity, IdentityUnavailableError

JWKS_URL = "https://{domain}/.well-known/jwks.json"
ISSUER = "https://{domain}/"
ALGORITHMS = ["RS256"]
TIMEOUT_SECONDS = 10.0
DOMAIN_SETTING, AUDIENCE_SETTING = "AUTH0_DOMAIN", "AUTH0_AUDIENCE"
EXPIRY_CLAIM, SUBJECT_CLAIM, KEY_ID_HEADER = "exp", "sub", "kid"


class Auth0Identity(Identity):
    def __init__(self, domain: str | None, audience: str | None, clock: Clock, transport: httpx2.BaseTransport | None = None) -> None:
        """Without `domain` and `audience`, sign-in is not set up and every check says so. `transport` replaces the
        network in tests."""
        self._domain = domain
        self._audience = audience
        self._clock = clock
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)
        self._keys: dict[str, jwt.PyJWK] = {}  # by key id

    def user_id(self, token: str | None) -> str | None:
        if not self._domain or not self._audience:
            raise IdentityUnavailableError(f"sign-in is not set up: set {DOMAIN_SETTING} and {AUDIENCE_SETTING} in .env")
        if not token:
            return None
        try:
            key_id = jwt.get_unverified_header(token).get(KEY_ID_HEADER)
        except jwt.InvalidTokenError:
            return None
        key = self._key(key_id) if isinstance(key_id, str) else None
        if key is None:
            return None
        try:
            # Expiry by our clock, below, rather than the system's.
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=ISSUER.format(domain=self._domain),
                options={"verify_exp": False, "verify_nbf": False, "verify_iat": False, "require": [EXPIRY_CLAIM, SUBJECT_CLAIM]},
            )
        except jwt.InvalidTokenError:
            return None
        if datetime.fromtimestamp(claims[EXPIRY_CLAIM], UTC) <= self._clock.now():
            return None
        subject = claims[SUBJECT_CLAIM]
        return subject if isinstance(subject, str) else None

    def _key(self, key_id: str) -> jwt.PyJWK | None:
        """The tenant's public key with this id, fetching its keys again when it is not known yet."""
        if key_id not in self._keys:
            self._keys = self._fetch_keys()
        return self._keys.get(key_id)

    def _fetch_keys(self) -> dict[str, jwt.PyJWK]:
        try:
            response = self._client.get(JWKS_URL.format(domain=self._domain))
            response.raise_for_status()
            keys = jwt.PyJWKSet.from_dict(json.loads(response.text))
        except (httpx2.HTTPError, ValueError, jwt.PyJWKSetError) as error:
            raise IdentityUnavailableError(f"Auth0: could not fetch the signing keys: {error}") from error
        return {key.key_id: key for key in keys.keys if key.key_id}
