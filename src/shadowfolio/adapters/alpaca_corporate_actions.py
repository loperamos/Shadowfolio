"""CorporateActions from Alpaca's corporate-actions API.

Development use only, like the rest of Alpaca's data (see alpaca_price_data).
"""

import json
from datetime import date
from decimal import Decimal

import httpx2

from shadowfolio.adapters.alpaca_price_data import BASE_URL, TIMEOUT_SECONDS, AlpacaConfig
from shadowfolio.domain.corporate_actions import SplitEvent
from shadowfolio.ports.corporate_actions import CorporateActions, CorporateActionsUnavailableError

CORPORATE_ACTIONS_PATH = "/v1/corporate-actions"
# Both kinds change the share count: a forward split multiplies it, a reverse split divides it.
SPLIT_TYPES = ("forward_split", "reverse_split")


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
        try:
            return self._splits(symbol, start, end)
        except httpx2.HTTPError as error:
            raise CorporateActionsUnavailableError(f"Alpaca: {error}") from error

    def _splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        events: list[SplitEvent] = []
        page_token: str | None = None
        while True:
            params = {"symbols": symbol, "types": ",".join(SPLIT_TYPES), "start": start.isoformat(), "end": end.isoformat()}
            if page_token:
                params["page_token"] = page_token
            response = self._client.get(CORPORATE_ACTIONS_PATH, params=params)
            response.raise_for_status()
            # Parse numbers as Decimal directly, never through float. Unknown symbols come back as 200, with none.
            body = json.loads(response.text, parse_float=Decimal)
            actions = body.get("corporate_actions") or {}
            for kind in (f"{split_type}s" for split_type in SPLIT_TYPES):
                for action in actions.get(kind) or []:
                    events.append(
                        SplitEvent(
                            symbol=action["symbol"],
                            ex_date=date.fromisoformat(action["ex_date"]),
                            old_rate=Decimal(action["old_rate"]),
                            new_rate=Decimal(action["new_rate"]),
                            event_id=action["id"],
                        )
                    )
            page_token = body.get("next_page_token")
            if not page_token:
                return sorted(events, key=lambda event: event.ex_date)
