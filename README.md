# Shadowfolio

Simulated investing wallets priced from real market data. See [SPEC.md](SPEC.md) for what we are building and [AGENTS.md](AGENTS.md) for how we work.

## Development

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                     # create .venv and install dev tools
uv run pytest               # tests
uv run pytest -m live       # contract tests against real providers (needs keys in .env, uses the network)
uv run ruff check           # lint
uv run ruff format --check  # formatting (drop --check to apply)
uv run mypy                 # type check
```

Format code with:
```bash
uv run ruff format
```

Configuration comes from environment variables, loaded from `.env` if present. Start from the template:
```bash
cp .env.example .env
```

```bash
# Run the API at http://127.0.0.1:8000 (docs at /docs)
uv run shadowfolio
```

After changing dependencies, run `uv lock` and commit `uv.lock`; CI installs with `uv sync --locked`.

## Daily sync

Corporate actions (splits) are applied to every wallet by `POST /api/sync`. Recording a trade also applies its symbol's splits first, so the daily run is what keeps holdings right as time passes. Locally it runs as a systemd user timer, every day at 07:00 New York time (before the US market opens), against the running backend:

```bash
./deploy/local/install-sync-timer.sh   # install and start the timer
loginctl enable-linger "$USER"          # optional: run it even when you are not logged in
systemctl --user list-timers shadowfolio-sync.timer
./deploy/local/uninstall-sync-timer.sh # stop and remove it (e.g. before moving the repo, then install again)
```

The timer reads the backend's address from `.env` at every run, and only the backend reads `SHADOWFOLIO_DB`, so changing either in `.env` needs no reinstall. Moving the repository does.

Lingering is a setting for all your user services, not part of the timer, so uninstalling leaves it as it is. If nothing else needs it, turn it off with `loginctl disable-linger "$USER"` (check it with `loginctl show-user "$USER" --property=Linger`).

## Agents (MCP)

The backend also serves an MCP server at `http://127.0.0.1:8000/mcp` (Streamable HTTP), so an agent can read your wallets and securities with the same figures as the web app. It is read-only for now, and has no sign-in yet: keep the backend on localhost. For example, with Claude Code:

```bash
claude mcp add --transport http shadowfolio http://127.0.0.1:8000/mcp
```

## Frontend

The web app lives in `web/` (Vite, React, TypeScript). It needs Node 24 LTS; with [nvm](https://github.com/nvm-sh/nvm), run `nvm use` inside `web/`.

```bash
cd web
npm install
npm run dev        # http://localhost:5173, with the backend running (uv run shadowfolio)
npm run generate   # after backend API changes: export the OpenAPI schema and regenerate src/api/generated
npm run build      # type-check and build
```

The API client in `web/src/api/generated` is generated from the backend's OpenAPI schema; never edit it by hand. In development the Vite dev server proxies API calls to the backend, so no CORS setup is needed.
