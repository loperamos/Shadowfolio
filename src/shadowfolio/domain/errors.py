"""Business rule violations raised by the domain."""


class DomainError(ValueError):
    """A request breaks a business rule."""


class InvalidNameError(DomainError):
    """A name is blank."""


class InvalidAmountError(DomainError):
    """An amount, quantity or price is out of range."""


class OperationTypeChangeError(DomainError):
    """An edit tries to turn an operation into another kind (e.g. a buy into a sell)."""


class InsufficientCashError(DomainError):
    """The wallet would not have enough cash at some point of its timeline."""


class InsufficientSharesError(DomainError):
    """The wallet would sell shares it did not hold at that point of its timeline."""


class MissingSettledAmountError(DomainError):
    """A trade in a foreign currency needs the amount settled in the wallet's currency."""


class MissingPriceCurrencyError(DomainError):
    """A trade's price is given without saying which currency it is in."""


class FutureTimestampError(DomainError):
    """An operation is dated after now."""


class PriceUnavailableError(DomainError):
    """There is no market price for a symbol (at a time) that needs one."""


class FxRateUnavailableError(DomainError):
    """There is no exchange rate for a currency pair that needs one."""


class OperationNotFoundError(LookupError):
    """The wallet has no operation with that id. Not a broken rule: the thing asked for does not exist."""
