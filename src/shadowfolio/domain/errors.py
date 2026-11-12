"""Business rule violations raised by the domain."""


class DomainError(ValueError):
    """A request breaks a business rule."""


class InvalidAmountError(DomainError):
    """An amount, quantity or price is out of range."""


class InsufficientCashError(DomainError):
    """The wallet would not have enough cash at some point of its timeline."""


class MissingSettledAmountError(DomainError):
    """A trade in a foreign currency needs the amount settled in the wallet's currency."""


class FutureTimestampError(DomainError):
    """An operation is dated after now."""
