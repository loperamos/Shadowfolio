# Shadowfolio

Simulated investing wallets priced from real market data. See [SPEC.md](SPEC.md) for what we are building and [AGENTS.md](AGENTS.md) for how we work.

## Development

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                     # create .venv and install dev tools
uv run pytest               # tests
uv run ruff check           # lint
uv run ruff format --check  # formatting (drop --check to apply)
uv run mypy                 # type check
```

After changing dependencies, run `uv lock` and commit `uv.lock`; CI installs with `uv sync --locked`.
