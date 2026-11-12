"""Write the HTTP API's OpenAPI schema to a file, without starting a server.

The frontend generates its TypeScript types from this file:
    uv run python -m shadowfolio.wiring.openapi web/openapi.json
"""

import json
import sys
from pathlib import Path

from shadowfolio.wiring.test import build_test_app


def main() -> None:
    # The routes and schemas are the same in every wiring; the test one needs no config or network.
    schema = build_test_app().openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
