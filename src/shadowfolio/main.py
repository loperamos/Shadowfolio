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
# The master key users' own market-data keys are encrypted with (a Fernet key); losing it loses those keys.
KEYS_SECRET_ENV = "SHADOWFOLIO_KEYS_SECRET"
HOST_ENV = "SHADOWFOLIO_HOST"
PORT_ENV = "SHADOWFOLIO_PORT"
# Optional: who SEC EDGAR is told is asking (an app name and a contact email); without it, no fundamentals.
SEC_EDGAR_CONTACT_ENV = "SEC_EDGAR_CONTACT"
FINNHUB_API_KEY_ENV = "FINNHUB_API_KEY"
MCP_ALLOWED_HOSTS_ENV = "SHADOWFOLIO_MCP_ALLOWED_HOSTS"
AUTH0_DOMAIN_ENV, AUTH0_CLIENT_ID_ENV, AUTH0_AUDIENCE_ENV = "AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_AUDIENCE"
EXISTING_WALLETS_OWNER_ENV = "SHADOWFOLIO_EXISTING_WALLETS_OWNER"
# The user ids that are admins, separated by commas: no plan limits, and they set other users' tiers.
ADMINS_ENV = "SHADOWFOLIO_ADMINS"
# Optional: the built web app (web/dist) for the backend to serve, as when deployed; without it, Vite serves it.
WEB_DIR_ENV = "SHADOWFOLIO_WEB_DIR"
# Whether the app runs the system's jobs itself (true when deployed), and the secret the jobs' endpoints need.
RUN_JOBS_ENV, JOB_TOKEN_ENV = "SHADOWFOLIO_RUN_JOBS", "SHADOWFOLIO_JOB_TOKEN"
TRUE = "true"
LIST_SEPARATOR = ","


class Environment(StrEnum):
    LOCAL = "local"


def main() -> None:
    config_dir = load_config()
    app = _build_app(Environment(_require_env(ENVIRONMENT_ENV)), config_dir)
    host = _require_env(HOST_ENV)
    port = int(_require_env(PORT_ENV))
    uvicorn.run(app, host=host, port=port)


def _build_app(environment: Environment, config_dir: Path) -> FastAPI:
    match environment:
        case Environment.LOCAL:
            return build_local_app(local_config(config_dir))


def local_config(config_dir: Path) -> LocalConfig:
    """The local wiring's configuration, from the environment (with .env loaded)."""
    alpaca = AlpacaConfig(key_id=_require_env(ALPACA_KEY_ID_ENV), secret_key=_require_env(ALPACA_SECRET_KEY_ENV))
    return LocalConfig(
        db_path=resolve_config_path(_require_env(DB_PATH_ENV), config_dir),
        alpaca=alpaca,
        keys_secret=_require_env(KEYS_SECRET_ENV),
        edgar_contact=os.environ.get(SEC_EDGAR_CONTACT_ENV),
        finnhub_key=os.environ.get(FINNHUB_API_KEY_ENV),
        auth0_domain=os.environ.get(AUTH0_DOMAIN_ENV) or None,
        auth0_client_id=os.environ.get(AUTH0_CLIENT_ID_ENV) or None,
        auth0_audience=os.environ.get(AUTH0_AUDIENCE_ENV) or None,
        existing_wallets_owner=os.environ.get(EXISTING_WALLETS_OWNER_ENV) or None,
        admins=_list(os.environ.get(ADMINS_ENV, "")),
        web_dir=resolve_config_path(web_dir, config_dir) if (web_dir := os.environ.get(WEB_DIR_ENV)) else None,
        run_jobs=os.environ.get(RUN_JOBS_ENV, "").strip().lower() == TRUE,
        job_token=os.environ.get(JOB_TOKEN_ENV) or None,
        mcp_allowed_hosts=_list(os.environ.get(MCP_ALLOWED_HOSTS_ENV, "")),
    )


def load_config() -> Path:
    """Load .env into the environment; returns the folder relative paths in it are from."""
    env_file = find_dotenv()  # searched upwards from this package, so found whatever folder the server starts in
    load_dotenv(env_file)
    # Relative paths in the config mean relative to the folder holding .env (the repo root), never to where the
    # server happens to be started; without a .env file, they are relative to the current folder.
    return Path(env_file).parent if env_file else Path.cwd()


def resolve_config_path(value: str, config_dir: Path) -> Path:
    """A path from the config: absolute paths as given, relative ones from `config_dir`."""
    path = Path(value)
    return path if path.is_absolute() else config_dir / path


def _list(value: str) -> tuple[str, ...]:
    """A list setting's items: separated by commas, blanks dropped."""
    return tuple(item.strip() for item in value.split(LIST_SEPARATOR) if item.strip())


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set; copy .env.example to .env and fill it in")
    return value


if __name__ == "__main__":
    main()
