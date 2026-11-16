"""Who a signed-in user is: from the token their sign-in gave them, to their user id. The sign-in provider (Auth0)
sits behind it, so it can be swapped."""

from abc import ABC, abstractmethod


class IdentityUnavailableError(Exception):
    """Sign-in cannot be checked now: the provider cannot be reached, or sign-in is not set up."""


class Identity(ABC):
    @abstractmethod
    def user_id(self, token: str | None) -> str | None:
        """The user the token was given to, if it is valid now (signed by the provider, for this app, not expired);
        None otherwise, or without a token.

        Raises IdentityUnavailableError when the provider cannot be asked.
        """
