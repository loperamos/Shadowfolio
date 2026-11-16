---
name: screenshot
description: Take a screenshot of Shadowfolio's web UI (a whole page or one area, optionally after clicks such as opening a dialog) with fresh backend and frontend servers running the current code. Use it to check how a UI change looks before handing it back, or when the user asks to see or screenshot the UI.
---

# Screenshot the web UI

The script starts its own backend (port 8765) and frontend (port 5199) with the current code, opens the page in headless
Chromium, saves a PNG and stops both servers. The developer's own servers (8000, 5173) are never touched. It reads the
repo's `.env`, so pages show the real local data and real market prices.

Its backend acts as one user without signing in (`python -m shadowfolio.wiring.screenshot`, listening on this machine
only): by default the developer, `SHADOWFOLIO_EXISTING_WALLETS_OWNER`; another with `--user <id>`. So signed-in pages
show that user's wallets, and the header shows their id instead of a name.

## Run it

From the repo root:

```bash
uv run python .claude/skills/screenshot/screenshot.py [PATH] [--area SELECTOR] [--click SELECTOR ...] [--wait-for SELECTOR] [--full-page] [--width W --height H] [--out FILE]
```

- `PATH`: the page, e.g. `/wallets` (default) or `/wallets/<id>`. Get wallet ids from the running app or `GET /api/wallets` on port 8765 while the script runs; simplest is to screenshot `/wallets` first.
- `--area`: capture only one element, using a Playwright selector: CSS (`table`, `.mantine-Modal-content`) or text (`text=Holdings`).
- `--click`: click something first, e.g. `--click "text=Add operation"` to open the dialog. Repeat for several steps.
- Default viewport 1280×800 at 2× pixel ratio. Output goes to `data/screenshots/` (gitignored) unless `--out` is given; the path is printed.

Examples:

```bash
uv run python .claude/skills/screenshot/screenshot.py /wallets
uv run python .claude/skills/screenshot/screenshot.py /wallets/<id> --area "table" 
uv run python .claude/skills/screenshot/screenshot.py /wallets/<id> --click "text=Add operation" --area ".mantine-Modal-content"
```

## Then

1. Open the PNG with the Read tool and look at it before describing it: alignment, spacing, overflow, empty or error states.
2. Show the user the path and what you checked; say what you could not judge from a static image (hover, focus, animations).

## Rules

- Only click things that open or show something (dialogs, menus, tabs). Never click actions that save, delete or change data: the servers use the real local database.
- If a server fails to start, the script prints the end of its log (`data/screenshots/backend.log` or `frontend.log`); a port already in use usually means a previous run is still alive. Report it rather than retrying in a loop.
