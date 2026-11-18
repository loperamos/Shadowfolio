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

## Sign-in

Users sign in with [Auth0](https://auth0.com), and each sees only their own wallets. In your Auth0 tenant, create a **Single Page Application** (allowed callback, logout and web origin: `http://localhost:5173`) and an **API** (its identifier is the audience, e.g. `https://shadowfolio/api`; turn on *Allow Offline Access* to stay signed in across reloads). Set `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID` and `AUTH0_AUDIENCE` in `.env`: none is a secret.

Auth0's sign-in only works on `https` or `localhost`. To use the app from another machine, open it as `localhost` through an SSH tunnel:

```bash
ssh -L 5173:localhost:5173 -L 8000:localhost:8000 <user>@<machine running Shadowfolio>
```

Wallets made before sign-in belong to no user: after your first sign-in, copy your user id from the menu under your name into `SHADOWFOLIO_EXISTING_WALLETS_OWNER` in `.env`, and restart the backend; they become yours, with their agents' tokens.

Signing in for the first time makes an account, on the free plan: 3 wallets, 20 orders a day, 2 agent tokens and 120 requests a minute (members: 10, 100, 10 and 600; `GET /api/me` says which). Put your own user id in `SHADOWFOLIO_ADMINS` to be an admin: no limits, and you can list users (`GET /api/users`) and put one on another tier (`PUT /api/users/<user id>/tier` with `{"tier": "member"}`; tiers are `free`, `member` and `admin`).

## Your own market-data keys

Each user saves their own Alpaca and Finnhub keys in Settings, so data fetched with a key is only shown to its owner. They are stored encrypted with `SHADOWFOLIO_KEYS_SECRET` (see `.env.example` to make one). The nightly backups hold the keys only encrypted; keep a copy of that master key apart from them, as without it the saved keys cannot be read.

## Self-hosting (Docker)

One image runs the backend, which also serves the built web app, so browser, API and MCP share one origin. Its data (the database and the market cache) lives in the `shadowfolio-data` volume, apart from the development servers' `data/`. Configuration comes from `.env` at run time; the container sets its own address, database path and web app.

```bash
docker compose up -d --build                    # the app alone, at http://127.0.0.1:8080 on this machine
docker compose --profile public up -d --build   # and the Cloudflare tunnel: live at your domain
docker compose logs -f app                      # follow it
```

The tunnel publishes the app on your domain through Cloudflare, with https and no open ports. Create it once from the command line, with the same `cloudflared` image, as your user so it can use `~/.cloudflared` (here for `shadowfolio.epole.dev`):

```bash
mkdir -p ~/.cloudflared && chmod 700 ~/.cloudflared
cloudflared() { docker run --rm -it --user "$(id -u):$(id -g)" -e HOME=/home/nonroot -v "$HOME/.cloudflared:/home/nonroot/.cloudflared" cloudflare/cloudflared:2026.10.1 "$@"; }
cloudflared tunnel login                                          # open the URL it prints, pick your domain: saves cert.pem
cloudflared tunnel create shadowfolio                             # prints the tunnel's id; saves <id>.json, its secret
cloudflared tunnel route dns shadowfolio shadowfolio.epole.dev   # the DNS record pointing the name at the tunnel
```

Then write `~/.cloudflared/config.yml`, with the id `create` printed:

```yaml
tunnel: <id>
credentials-file: /etc/cloudflared/<id>.json
ingress:
  - hostname: shadowfolio.epole.dev
    service: http://app:8000
  - service: http_status:404
```

`cert.pem` is only needed to create tunnels and DNS records: move it somewhere safe once done. In Auth0, add `https://shadowfolio.epole.dev` to the application's allowed callback, logout and web origin URLs.

To start the container from a copy of the development database (SQLite's online backup, safe while the development backend runs), before its first start:

```bash
docker compose run --rm --no-deps --user root -v "$PWD/data:/seed:ro" app python -c "
import os, pwd, sqlite3
for name in ('shadowfolio.db', 'market-cache.db'):
    source, copy = sqlite3.connect(f'file:/seed/{name}?mode=ro', uri=True), sqlite3.connect(f'/data/{name}')
    source.backup(copy)
    copy.close()
    os.chown(f'/data/{name}', pwd.getpwnam('shadowfolio').pw_uid, -1)
"
```

Back up the container's database every night (03:30) to `~/shadowfolio-backups` (or `SHADOWFOLIO_BACKUP_DIR`), keeping 14 days, with a systemd user timer; it is on the same disk, so copy that folder elsewhere to survive a failed disk:

```bash
./deploy/docker/install-backup-timer.sh     # install and start the timer
./deploy/docker/backup-db.sh                # one backup now
./deploy/docker/uninstall-backup-timer.sh   # stop and remove the timer (the backups stay)
```

To restore one, stop the app and copy it over `/data/shadowfolio.db` in the volume, as the seeding above does.

Going live, in order:

1. The tunnel exists, with its DNS record and `~/.cloudflared/config.yml` (above).
2. Auth0: the domain in the application's allowed URLs, and only invited people let in (e.g. an Action on login that only allows a list of emails for this application).
3. `.env`: the domain in `SHADOWFOLIO_MCP_ALLOWED_HOSTS` (e.g. `shadowfolio.epole.dev`), and `SHADOWFOLIO_JOB_TOKEN` set.
4. The container's data: freshly copied from the development database if that is where your wallets are (above), as from then on the container's is the one in use.
5. `docker compose --profile public up -d --build`, then open the domain and sign in.

## Daily sync

Corporate actions (splits and dividends) are applied to every wallet by `POST /api/sync`. Recording a trade also applies its symbol's splits first, so the daily run is what keeps holdings right as time passes.

The Docker container runs it itself, when it starts and every day at 07:00 New York time, and fills due orders every minute (`SHADOWFOLIO_RUN_JOBS=true`). The jobs' endpoints (`POST /api/sync`, `POST /api/orders/fill`) need the job secret, `Authorization: Bearer <SHADOWFOLIO_JOB_TOKEN>`, and are closed without one configured, so the public cannot trigger them.

For the development servers, it runs as a systemd user timer, every day at 07:00 New York time (before the US market opens), against the running backend, sending the job secret from `.env`:

```bash
./deploy/local/install-sync-timer.sh   # install and start the timer
loginctl enable-linger "$USER"          # optional: run it even when you are not logged in
systemctl --user list-timers shadowfolio-sync.timer
./deploy/local/uninstall-sync-timer.sh # stop and remove it (e.g. before moving the repo, then install again)
```

The timer reads the backend's address from `.env` at every run, and only the backend reads `SHADOWFOLIO_DB`, so changing either in `.env` needs no reinstall. Moving the repository does.

Lingering is a setting for all your user services, not part of the timer, so uninstalling leaves it as it is. If nothing else needs it, turn it off with `loginctl disable-linger "$USER"` (check it with `loginctl show-user "$USER" --property=Linger`).

## Agents (MCP)

The backend also serves an MCP server at `http://127.0.0.1:8000/mcp` (Streamable HTTP), so an agent can read your wallets and securities with the same figures as the web app, and preview, place and cancel orders now (never back-dated), each with its reason. It answers on localhost, plus any address listed in `SHADOWFOLIO_MCP_ALLOWED_HOSTS` (see `.env.example`).

Every request needs an access token, with a scope (`read`, or `trading`: read and place or cancel orders) and the wallets it may use. Create one in the web app's **Agent access** page (or `POST /api/access-tokens`); its secret is shown once. Then give it to the agent as a header, e.g. with Claude Code:

```bash
claude mcp add --transport http shadowfolio http://127.0.0.1:8000/mcp --header "Authorization: Bearer <secret>"
```

Revoke a token in the same page. The web API itself has no sign-in yet (it comes with accounts), so anyone who can reach it can create tokens: keep it on a network you trust.

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
