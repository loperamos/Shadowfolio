"""How the Alpaca corporate-actions adapter reads splits, with the network replaced by a fake transport.

The fake pages below are trimmed from real answers; the live contract test checks the real API.
"""

import json
from datetime import date
from decimal import Decimal

import httpx2

from shadowfolio.adapters.alpaca_corporate_actions import AlpacaCorporateActions
from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.domain.corporate_actions import SplitEvent

CONFIG = AlpacaConfig(key_id="test-key", secret_key="test-secret")

FIRST_PAGE = {
    "corporate_actions": {"forward_splits": [{"symbol": "NVDA", "ex_date": "2024-06-10", "old_rate": 1, "new_rate": 10, "id": "fwd-1"}]},
    "next_page_token": "page-2",
}
SECOND_PAGE = {
    "corporate_actions": {"reverse_splits": [{"symbol": "XYZ", "ex_date": "2024-02-01", "old_rate": 10, "new_rate": 1, "id": "rev-1"}]},
    "next_page_token": None,
}


def test_forward_and_reverse_splits_are_read_from_every_page_oldest_first() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        page = SECOND_PAGE if request.url.params.get("page_token") == "page-2" else FIRST_PAGE
        return httpx2.Response(200, text=json.dumps(page))

    splits = AlpacaCorporateActions(CONFIG, transport=httpx2.MockTransport(handler)).splits("NVDA", date(2024, 1, 1), date(2024, 12, 31))

    assert splits == [
        SplitEvent("XYZ", date(2024, 2, 1), Decimal(10), Decimal(1), "rev-1"),
        SplitEvent("NVDA", date(2024, 6, 10), Decimal(1), Decimal(10), "fwd-1"),
    ]
    first = seen[0].url
    assert (first.path, first.params["symbols"], first.params["types"]) == ("/v1/corporate-actions", "NVDA", "forward_split,reverse_split")
    assert len(seen) == 2


def test_no_actions_means_no_splits() -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, text='{"corporate_actions": {}, "next_page_token": null}'))
    assert AlpacaCorporateActions(CONFIG, transport=transport).splits("ZZZZ", date(2024, 1, 1), date(2024, 12, 31)) == []
