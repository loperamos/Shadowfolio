"""When deployed, the backend also serves the built web app, so browser and API share one origin: every path that is
neither the API nor the MCP server gets the app (its files, or its page for the app's own routes, which the browser
then shows)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shadowfolio.wiring.test import build_test_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Shadowfolio</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log('app')")
    return TestClient(build_test_app(web_dir=tmp_path), base_url="http://127.0.0.1:8000")


def test_the_web_app_and_its_files_are_served(client: TestClient) -> None:
    page = client.get("/")
    script = client.get("/assets/app.js")

    assert (page.status_code, "Shadowfolio" in page.text) == (200, True)
    assert (script.status_code, script.text) == (200, "console.log('app')")


@pytest.mark.parametrize("path", ["/wallets", "/wallets/2d0b7c1e-0000-0000-0000-000000000000", "/securities/compare?symbols=NVDA"])
def test_the_apps_own_routes_get_its_page(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert (response.status_code, "Shadowfolio" in response.text) == (200, True)


def test_the_api_and_the_mcp_server_are_still_theirs(client: TestClient) -> None:
    assert client.get("/api/wallets").status_code == 200  # as the tests' signed-in user
    assert client.get("/api/nothing-here").status_code == 404  # not the app's page
    assert client.post("/mcp", json={}).status_code == 401  # needs an agent's token
    assert client.get("/assets/missing.js").status_code == 404
