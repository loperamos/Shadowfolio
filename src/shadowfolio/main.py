"""Backend entry point: reads config, builds the app for the chosen environment and serves it."""

import os
from enum import StrEnum
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.wiring.local import LocalConfig, build_local_app

ENVIRONMENT_ENV = "SHADOWFOLIO_ENV"
DB_PATH_ENV = "SHADOWFOLIO_DB"
ALPACA_KEY_ID_ENV = "ALPACA_API_KEY_ID"
ALPACA_SECRET_KEY_ENV = "ALPACA_API_SECRET_KEY"
HOST_ENV = "SHADOWFOLIO_HOST"
PORT_ENV = "SHADOWFOLIO_PORT"


class Environment(StrEnum):
    LOCAL = "local"


def main() -> None:
    load_dotenv()
    app = _build_app(Environment(_require_env(ENVIRONMENT_ENV)))
    host = _require_env(HOST_ENV)
    port = int(_require_env(PORT_ENV))
    uvicorn.run(app, host=host, port=port)


def _build_app(environment: Environment) -> FastAPI:
    match environment:
        case Environment.LOCAL:
            alpaca = AlpacaConfig(key_id=_require_env(ALPACA_KEY_ID_ENV), secret_key=_require_env(ALPACA_SECRET_KEY_ENV))
            return build_local_app(LocalConfig(db_path=Path(_require_env(DB_PATH_ENV)), alpaca=alpaca))


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set; copy .env.example to .env and fill it in")
    return value


if __name__ == "__main__":
    main()
