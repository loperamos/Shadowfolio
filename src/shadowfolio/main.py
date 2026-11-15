"""Backend entry point: reads config, builds the app for the chosen environment and serves it."""

import os
from enum import StrEnum
from pathlib import Path

import uvicorn
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI

from shadowfolio.adapters.alpaca_price_data import AlpacaConfig
from shadowfolio.wiring.local import LocalConfig, build_local_app

ENVIRONMENT_ENV = "SHADOWFOLIO_ENV"
DB_PATH_ENV = "SHADOWFOLIO_DB"
ALPACA_KEY_ID_ENV = "ALPACA_API_KEY_ID"
ALPACA_SECRET_KEY_ENV = "ALPACA_API_SECRET_KEY"
HOST_ENV = "SHADOWFOLIO_HOST"
PORT_ENV = "SHADOWFOLIO_PORT"
# Optional: who SEC EDGAR is told is asking (an app name and a contact email); without it, no fundamentals.
SEC_EDGAR_CONTACT_ENV = "SEC_EDGAR_CONTACT"


class Environment(StrEnum):
    LOCAL = "local"


def main() -> None:
    env_file = find_dotenv()  # searched upwards from this package, so found whatever folder the server starts in
    load_dotenv(env_file)
    # Relative paths in the config mean relative to the folder holding .env (the repo root), never to where the
    # server happens to be started; without a .env file, they are relative to the current folder.
    config_dir = Path(env_file).parent if env_file else Path.cwd()
    app = _build_app(Environment(_require_env(ENVIRONMENT_ENV)), config_dir)
    host = _require_env(HOST_ENV)
    port = int(_require_env(PORT_ENV))
    uvicorn.run(app, host=host, port=port)


def _build_app(environment: Environment, config_dir: Path) -> FastAPI:
    match environment:
        case Environment.LOCAL:
            alpaca = AlpacaConfig(key_id=_require_env(ALPACA_KEY_ID_ENV), secret_key=_require_env(ALPACA_SECRET_KEY_ENV))
            db_path = resolve_config_path(_require_env(DB_PATH_ENV), config_dir)
            return build_local_app(LocalConfig(db_path=db_path, alpaca=alpaca, edgar_contact=os.environ.get(SEC_EDGAR_CONTACT_ENV)))


def resolve_config_path(value: str, config_dir: Path) -> Path:
    """A path from the config: absolute paths as given, relative ones from `config_dir`."""
    path = Path(value)
    return path if path.is_absolute() else config_dir / path


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set; copy .env.example to .env and fill it in")
    return value


if __name__ == "__main__":
    main()
