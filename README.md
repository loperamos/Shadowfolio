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
