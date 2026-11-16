"""Screenshot the web UI as it is now: start fresh servers with the current code, open a page, capture it, stop them.

The servers run on their own ports, so the developer's own servers are never touched. They use the repo's .env, so
the screenshots show the real local data.

    uv run python .claude/skills/screenshot/screenshot.py /wallets
    uv run python .claude/skills/screenshot/screenshot.py /wallets/<id> --area "table"
    uv run python .claude/skills/screenshot/screenshot.py /wallets/<id> --click "text=Add operation" --area ".mantine-Modal-content"
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
HOST = "127.0.0.1"
BACKEND_PORT = 8765
FRONTEND_PORT = 5199
CHROMIUM = "/usr/bin/chromium"
OUT_DIR = REPO / "data" / "screenshots"  # under data/, so it is gitignored
STARTUP_TIMEOUT_SECONDS = 60
STOP_TIMEOUT_SECONDS = 10
SETTLE_MS = 600  # lets dialogs and menus finish opening before the capture
PIXEL_RATIO = 2  # crisp images for people to look at

# The frontend needs Node from nvm, which is only loaded by an interactive shell.
FRONTEND_COMMAND = (
    f'. "$HOME/.nvm/nvm.sh" --no-use && nvm use --silent >/dev/null && exec npx vite --host {HOST} --port {FRONTEND_PORT} --strictPort'
)


def main() -> None:
    args = _parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"{datetime.now(UTC):%Y%m%d-%H%M%S}.png"
    env = os.environ | {"SHADOWFOLIO_HOST": HOST, "SHADOWFOLIO_PORT": str(BACKEND_PORT)}

    with _server("backend", ["uv", "run", "shadowfolio"], REPO, env, f"http://{HOST}:{BACKEND_PORT}/api/auth/config"):
        with _server("frontend", ["bash", "-c", FRONTEND_COMMAND], REPO / "web", env, f"http://{HOST}:{FRONTEND_PORT}/"):
            _capture(f"http://{HOST}:{FRONTEND_PORT}{args.path}", args, out)
    print(out)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default="/wallets", help="page to open, e.g. /wallets/<id>")
    parser.add_argument("--area", help="capture only the first element matching this Playwright selector")
    parser.add_argument("--click", action="append", default=[], help="Playwright selector to click before capturing; repeatable")
    parser.add_argument("--wait-for", help="Playwright selector to wait for before capturing")
    parser.add_argument("--full-page", action="store_true", help="capture the whole scrollable page")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--out", help=f"PNG path (default: a timestamped file in {OUT_DIR.relative_to(REPO)})")
    return parser.parse_args()


def _capture(url: str, args: argparse.Namespace, out: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=PIXEL_RATIO)
            page.goto(url)
            page.wait_for_load_state("networkidle")
            for selector in args.click:
                page.locator(selector).first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(SETTLE_MS)
            if args.wait_for:
                page.locator(args.wait_for).first.wait_for()
            if args.area:
                page.locator(args.area).first.screenshot(path=out)
            else:
                page.screenshot(path=out, full_page=args.full_page)
        finally:
            browser.close()


@contextmanager
def _server(name: str, command: list[str], cwd: Path, env: dict[str, str], ready_url: str) -> Iterator[None]:
    """Run a server in its own process group until the block ends; fail clearly if it does not come up."""
    log_path = OUT_DIR / f"{name}.log"
    with open(log_path, "w") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            _wait_until_up(name, process, ready_url, log_path)
            yield
        finally:
            _stop(process, log)


def _wait_until_up(name: str, process: subprocess.Popen[bytes], url: str, log_path: Path) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            sys.exit(f"{name} stopped while starting (port in use?). Last lines of {log_path}:\n{_tail(log_path)}")
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    sys.exit(f"{name} did not answer at {url} within {STARTUP_TIMEOUT_SECONDS}s. Last lines of {log_path}:\n{_tail(log_path)}")


def _stop(process: subprocess.Popen[bytes], log: IO[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
    log.flush()


def _tail(path: Path, lines: int = 15) -> str:
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


if __name__ == "__main__":
    main()
