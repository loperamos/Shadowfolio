"""Identity from a table of tokens, for tests."""

from shadowfolio.ports.identity import Identity, IdentityUnavailableError


class InMemoryIdentity(Identity):
    def __init__(self, users: dict[str, str], anonymous: str | None = None, unavailable: str | None = None) -> None:
        """`users` maps tokens to user ids. `anonymous` is who a request without a token is (e.g. one user for tests
        that are not about sign-in); `unavailable` makes every check fail with that message."""
        self._users = users
        self._anonymous = anonymous
        self._unavailable = unavailable

    def user_id(self, token: str | None) -> str | None:
        if self._unavailable is not None:
            raise IdentityUnavailableError(self._unavailable)
        return self._anonymous if token is None else self._users.get(token)
