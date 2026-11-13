"""CorporateActions from Alpaca's corporate-actions API.

Development use only, like the rest of Alpaca's data (see alpaca_price_data).
"""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import httpx2

from shadowfolio.adapters.alpaca_price_data import BASE_URL, TIMEOUT_SECONDS, AlpacaConfig
from shadowfolio.domain.corporate_actions import DividendEvent, SplitEvent
from shadowfolio.domain.money import Currency
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError

CORPORATE_ACTIONS_PATH = "/v1/corporate-actions"
# Both kinds change the share count: a forward split multiplies it, a reverse split divides it.
SPLIT_TYPES = ("forward_split", "reverse_split")
DIVIDEND_TYPE = "cash_dividend"
# Alpaca covers US listings only, whose cash dividends are paid in dollars; its data has no currency field, so the
# currency is stated here. A provider covering other markets must report each dividend's currency.
DIVIDEND_CURRENCY = Currency.USD


class AlpacaCorporateActions(CorporateActions):
    def __init__(self, config: AlpacaConfig, transport: httpx2.BaseTransport | None = None) -> None:
        """`transport` replaces the network in tests."""
        self._client = httpx2.Client(
            base_url=BASE_URL,
            headers={"APCA-API-KEY-ID": config.key_id, "APCA-API-SECRET-KEY": config.secret_key},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        """Alpaca filters by process date, which for a split is its ex-date."""
        events = [
            SplitEvent(
                symbol=action["symbol"],
                ex_date=date.fromisoformat(action["ex_date"]),
                old_rate=Decimal(action["old_rate"]),
                new_rate=Decimal(action["new_rate"]),
                event_id=action["id"],
            )
            for action in self._actions(symbol, SPLIT_TYPES, start, end)
        ]
        return sorted(events, key=lambda event: event.ex_date)

    def dividends(self, symbol: str, start: date, end: date) -> list[DividendEvent]:
        """Alpaca filters by process date, which for a cash dividend is its payment date, or its ex-date when the
        payment date is unknown."""
        events = [
            DividendEvent(
                symbol=action["symbol"],
                ex_date=date.fromisoformat(action["ex_date"]),
                # Missing on dividends before about April 2020.
                payable_date=date.fromisoformat(action["payable_date"]) if action.get("payable_date") else None,
                per_share=Decimal(action["rate"]),
                currency=DIVIDEND_CURRENCY,
                event_id=action["id"],
            )
            for action in self._actions(symbol, (DIVIDEND_TYPE,), start, end)
        ]
        return sorted(events, key=lambda event: event.payable_date or event.ex_date)

    def _actions(self, symbol: str, types: tuple[str, ...], start: date, end: date) -> list[dict[str, Any]]:
        """Every action of these types, from all pages. Fails as unavailable on any HTTP problem."""
        try:
            return self._fetch_actions(symbol, types, start, end)
        except httpx2.HTTPError as error:
            raise CorporateActionsUnavailableError(f"Alpaca: {error}") from error

    def _fetch_actions(self, symbol: str, types: tuple[str, ...], start: date, end: date) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {"symbols": symbol, "types": ",".join(types), "start": start.isoformat(), "end": end.isoformat()}
            if page_token:
                params["page_token"] = page_token
            response = self._client.get(CORPORATE_ACTIONS_PATH, params=params)
            response.raise_for_status()
            # Parse numbers as Decimal directly, never through float. Unknown symbols come back as 200, with none.
            body = json.loads(response.text, parse_float=Decimal)
            by_kind = body.get("corporate_actions") or {}
            for kind in (f"{action_type}s" for action_type in types):
                actions.extend(by_kind.get(kind) or [])
            page_token = body.get("next_page_token")
            if not page_token:
                return actions
