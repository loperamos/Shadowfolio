"""Identity where every request is one user's, signed in or not: for screenshots and checks of signed-in pages on the
developer's machine (see wiring.screenshot). Never in an app others can reach."""

from shadowfolio.ports.identity import Identity


class FixedIdentity(Identity):
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def user_id(self, token: str | None) -> str | None:
        return self._user_id
