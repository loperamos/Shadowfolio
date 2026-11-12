"""Guards the layer rules from AGENTS.md by inspecting imports."""

import ast
from pathlib import Path

import pytest

PACKAGE = "shadowfolio"
SRC = Path(__file__).resolve().parents[1] / "src" / PACKAGE

# Layers each layer must not import.
FORBIDDEN_LAYERS = {
    "domain": {"usecases", "ports", "adapters", "interfaces"},
    "ports": {"usecases", "adapters", "interfaces"},
    "usecases": {"adapters", "interfaces"},
}

# Modules the pure domain must not import (I/O, network, environment).
DOMAIN_FORBIDDEN_MODULES = {"http", "httpx", "io", "os", "pathlib", "requests", "shutil", "socket", "sqlite3", "subprocess", "urllib"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _files(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_LAYERS))
def test_layer_does_not_import_outer_layers(layer: str) -> None:
    forbidden = {f"{PACKAGE}.{name}" for name in FORBIDDEN_LAYERS[layer]}
    for path in _files(layer):
        for name in _imports(path):
            assert not any(name == f or name.startswith(f + ".") for f in forbidden), f"{path.relative_to(SRC)} imports {name}"


def test_domain_does_no_io() -> None:
    for path in _files("domain"):
        for name in _imports(path):
            assert name.split(".")[0] not in DOMAIN_FORBIDDEN_MODULES, f"{path.relative_to(SRC)} imports {name}"
